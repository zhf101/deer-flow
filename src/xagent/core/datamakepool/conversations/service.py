from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from xagent.web.models.chat_message import TaskChatMessage
from xagent.web.models.dm_flow_draft import DMFlowDraft
from xagent.web.models.task import Task, TaskStatus
from xagent.web.models.user import User
from xagent.web.services.chat_history_service import (
    persist_assistant_message,
    persist_user_message,
)

from ..contracts import FlowDraftStatus
from ..flowdraft import FlowDraftService
from ..snapshots import SnapshotService


@dataclass
class ConversationService:
    """探索态聊天入口服务。

    这一层只负责 Phase 1 的最小闭环：

    1. 复用 `Task` 作为探索态会话宿主
    2. 复用 `TaskChatMessage` 持久化聊天历史
    3. 生成或更新当前会话对应的最小 `FlowDraft`

    当前实现明确不做：
    - LLM 自动规划
    - 多草稿并存
    - 聊天修正版本化策略扩展
    """

    db: Session
    flowdraft_service: FlowDraftService | None = None
    snapshot_service: SnapshotService | None = None

    def create_conversation(
        self,
        user: User,
        *,
        title: str | None = None,
        objective: str | None = None,
    ) -> dict[str, Any]:
        """创建一个新的探索态会话。

        设计上继续沿用 `Task` 作为会话宿主，避免再引入一套独立 Conversation
        模型，确保后续聊天、FlowDraft、试跑与运行桥接仍围绕同一宿主聚合。
        """

        normalized_title = self._normalize_text(title) or "新建探索会话"
        normalized_objective = self._normalize_text(objective)

        task = Task(
            user_id=int(user.id),
            title=normalized_title,
            description=normalized_objective,
            status=TaskStatus.PENDING,
        )
        self.db.add(task)
        self.db.flush()

        flowdraft = DMFlowDraft(
            task_id=int(task.id),
            status=FlowDraftStatus.DRAFT.value,
            title=normalized_title,
            objective=normalized_objective,
            business_graph_payload={},
            technical_graph_payload={},
            pending_issues_payload=[],
            preflight_summary_payload=None,
            input_schema_draft=self._build_input_schema_draft(normalized_objective),
            output_mapping_draft={},
            created_by=int(user.id),
        )
        self.db.add(flowdraft)
        self.db.commit()
        self.db.refresh(task)
        self.db.refresh(flowdraft)
        return self._serialize_conversation(task, flowdraft)

    def post_message(
        self,
        conversation_id: int,
        content: str,
        user: User,
    ) -> dict[str, Any]:
        """向探索态会话追加一条用户消息，并重算当前初版 FlowDraft。

        当前策略仍以“基于完整用户消息转录重算 bootstrap 草稿”为主，但会补一层
        最小保护：
        - bootstrap 草稿上的已选资产引用会尽量保留
        - 如果技术图已经进入人工修正阶段，则不再被新的聊天消息整体覆盖
        """

        normalized_content = self._normalize_text(content)
        if not normalized_content:
            raise ValueError("Conversation message content is required")

        task = self._get_conversation_task(conversation_id, user)
        flowdraft = self._ensure_flowdraft(task, user)

        message = persist_user_message(
            db=self.db,
            task_id=int(task.id),
            user_id=int(user.id),
            content=normalized_content,
        )
        if message is None:
            raise ValueError("Conversation message content is required")

        transcript = self._load_user_messages(int(task.id))
        generated = self._build_initial_flowdraft_payload(transcript)
        technical_graph = self._merge_generated_technical_graph(
            existing_graph=flowdraft.technical_graph_payload or {},
            generated_graph=generated["technical_graph"],
            message_count=len(transcript),
        )
        preflight_summary = self._flowdraft_service().evaluate_preflight(
            technical_graph
        )
        pending_issues = preflight_summary.get("issues", [])

        flowdraft.title = generated["title"]
        flowdraft.objective = generated["objective"]
        flowdraft.business_graph_payload = generated["business_graph"]
        flowdraft.technical_graph_payload = technical_graph
        flowdraft.pending_issues_payload = pending_issues
        flowdraft.preflight_summary_payload = preflight_summary
        flowdraft.input_schema_draft = generated["input_schema_draft"]
        flowdraft.output_mapping_draft = generated["output_mapping_draft"]
        flowdraft.status = self._derive_status(preflight_summary)

        # Task 仍是探索态宿主，需要同步标题与摘要，便于后续列表页复用。
        task.title = generated["title"]
        task.description = generated["objective"]

        if flowdraft.latest_snapshot_id is None:
            self._snapshot_service().create_snapshot(
                flowdraft=flowdraft,
                snapshot_type="initial_draft",
                created_by=int(user.id),
            )

        self.db.commit()
        self.db.refresh(flowdraft)

        assistant_summary = self._build_assistant_summary(pending_issues)
        assistant_message = persist_assistant_message(
            db=self.db,
            task_id=int(task.id),
            user_id=int(user.id),
            content=assistant_summary,
            message_type="flowdraft_summary",
        )

        return {
            "conversation_id": int(task.id),
            "message_id": int(message.id),
            "assistant_message_id": (
                int(assistant_message.id) if assistant_message is not None else None
            ),
            "flowdraft_id": int(flowdraft.id),
            "flowdraft_status": flowdraft.status,
            "title": flowdraft.title,
            "objective": flowdraft.objective,
            "assistant_summary": assistant_summary,
            "pending_issues": pending_issues,
            "latest_snapshot_id": flowdraft.latest_snapshot_id,
        }

    def get_conversation_flowdraft(
        self,
        conversation_id: int,
        user: User,
    ) -> dict[str, Any]:
        """读取会话当前关联的 FlowDraft。"""

        task = self._get_conversation_task(conversation_id, user)
        flowdraft = self._ensure_flowdraft(task, user)
        return self._flowdraft_service().get_flowdraft(int(flowdraft.id), user)

    def _get_conversation_task(self, conversation_id: int, user: User) -> Task:
        """按保守权限策略读取探索态会话宿主。

        `Task` 目前没有稳定的 `system_short` 归属，因此这里延续保守边界：
        - 系统管理员可读
        - 任务拥有者可读
        """

        task = self.db.query(Task).filter(Task.id == conversation_id).first()
        if task is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        if user.is_admin or int(task.user_id) == int(user.id):
            return task
        raise PermissionError(f"User {user.id} cannot access conversation {conversation_id}")

    def _ensure_flowdraft(self, task: Task, user: User) -> DMFlowDraft:
        """确保每个探索态会话至少存在一个 FlowDraft。"""

        flowdraft = (
            self.db.query(DMFlowDraft)
            .filter(DMFlowDraft.task_id == task.id)
            .order_by(DMFlowDraft.updated_at.desc(), DMFlowDraft.id.desc())
            .first()
        )
        if flowdraft is not None:
            return flowdraft

        flowdraft = DMFlowDraft(
            task_id=int(task.id),
            status=FlowDraftStatus.DRAFT.value,
            title=task.title,
            objective=task.description,
            business_graph_payload={},
            technical_graph_payload={},
            pending_issues_payload=[],
            preflight_summary_payload=None,
            input_schema_draft=self._build_input_schema_draft(task.description),
            output_mapping_draft={},
            created_by=int(user.id),
        )
        self.db.add(flowdraft)
        self.db.flush()
        return flowdraft

    def _load_user_messages(self, task_id: int) -> list[str]:
        """只读取用户消息，避免系统摘要反向污染初版草稿生成。"""

        rows = (
            self.db.query(TaskChatMessage)
            .filter(
                TaskChatMessage.task_id == task_id,
                TaskChatMessage.role == "user",
            )
            .order_by(TaskChatMessage.id.asc())
            .all()
        )
        return [
            normalized
            for row in rows
            if (normalized := self._normalize_text(row.content)) is not None
        ]

    def _build_initial_flowdraft_payload(
        self,
        transcript: list[str],
    ) -> dict[str, Any]:
        """根据当前聊天转录生成最小初版 FlowDraft 结构。

        这里刻意采用确定性规则而不是 LLM 推理，目标是先把后端主链路
        接通，并为后续真正的“聊天收敛”保留清晰替换点。
        """

        latest_message = transcript[-1] if transcript else "待补充探索目标"
        title = self._build_title(latest_message)
        objective = self._build_objective(transcript)

        business_graph = {
            "nodes": [
                {
                    "id": "goal_1",
                    "node_type": "objective",
                    "title": title,
                    "summary": objective,
                    "status": "draft",
                }
            ],
            "edges": [],
            "meta": {
                "generation_mode": "conversation_bootstrap",
                "message_count": len(transcript),
            },
        }

        technical_graph = {
            "nodes": [
                {
                    "id": "start",
                    "step_id": "start",
                    "step_type": "start",
                    "step_name": "开始",
                    "depends_on": [],
                    "pending_flags": [],
                    "resolved_execution_plan": {},
                },
                {
                    "id": "intent_planning",
                    "step_id": "intent_planning",
                    "step_type": "mapping",
                    "step_name": "待收敛执行路线",
                    "depends_on": ["start"],
                    "pending_flags": [
                        "route_pending",
                        "asset_pending",
                        "param_pending",
                    ],
                    "design_intent": {
                        "objective": objective,
                        "latest_user_message": latest_message,
                        "conversation_stage": "exploration",
                    },
                    "mapping": {},
                    "output_mapping": {},
                    "resolution_rationale": {
                        "summary": (
                            "当前只完成聊天目标抽取，尚未收敛到具体资产、参数和输出映射。"
                        )
                    },
                    "resolved_execution_plan": {
                        "mapping": {},
                        "output_mapping": {},
                    },
                    "editable_fields": [
                        {
                            "name": "mapping",
                            "mode": "direct_edit",
                            "widget": "json",
                            "required": False,
                        },
                        {
                            "name": "output_mapping",
                            "mode": "direct_edit",
                            "widget": "json",
                            "required": False,
                        },
                    ],
                },
                {
                    "id": "end",
                    "step_id": "end",
                    "step_type": "end",
                    "step_name": "结束",
                    "depends_on": ["intent_planning"],
                    "pending_flags": [],
                    "resolved_execution_plan": {},
                },
            ],
            "edges": [
                {"from": "start", "to": "intent_planning"},
                {"from": "intent_planning", "to": "end"},
            ],
            "meta": {
                "generation_mode": "conversation_bootstrap",
                "message_count": len(transcript),
            },
        }

        return {
            "title": title,
            "objective": objective,
            "business_graph": business_graph,
            "technical_graph": technical_graph,
            "input_schema_draft": self._build_input_schema_draft(objective),
            "output_mapping_draft": {},
        }

    def _merge_generated_technical_graph(
        self,
        *,
        existing_graph: dict[str, Any],
        generated_graph: dict[str, Any],
        message_count: int,
    ) -> dict[str, Any]:
        """把聊天重算结果与现有技术图做最小合并。

        目标只有两个：
        1. 当草稿仍处于 bootstrap 阶段时，保留已选中的资产引用与版本快照
        2. 当技术图已经进入人工修正阶段时，避免一条聊天消息把现有设计整体覆盖掉
        """

        if self._should_preserve_existing_graph(existing_graph):
            preserved_graph = dict(existing_graph or {})
            meta = dict(preserved_graph.get("meta") or {})
            meta["conversation_message_count"] = message_count
            meta.setdefault("generation_mode", "conversation_preserved")
            preserved_graph["meta"] = meta
            return preserved_graph

        merged_graph = {
            **(generated_graph or {}),
            "nodes": [dict(node) for node in (generated_graph.get("nodes") or [])],
            "edges": list(generated_graph.get("edges") or []),
        }
        existing_nodes = {
            str(node.get("step_id") or node.get("id") or ""): node
            for node in (existing_graph.get("nodes") or [])
            if isinstance(node, dict)
        }
        for node in merged_graph["nodes"]:
            step_id = str(node.get("step_id") or node.get("id") or "")
            existing_node = existing_nodes.get(step_id)
            if not isinstance(existing_node, dict):
                continue
            asset_ref = existing_node.get("asset_ref")
            snapshot_ref = existing_node.get("asset_version_snapshot_ref")
            if asset_ref is not None:
                node["asset_ref"] = asset_ref
                plan = dict(node.get("resolved_execution_plan") or {})
                plan.setdefault("asset_ref", asset_ref)
                node["resolved_execution_plan"] = plan
            if snapshot_ref is not None:
                node["asset_version_snapshot_ref"] = snapshot_ref
        return merged_graph

    def _should_preserve_existing_graph(self, technical_graph: dict[str, Any]) -> bool:
        """判断当前技术图是否已超出 bootstrap 覆盖边界。"""

        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            step_type = str(node.get("step_type") or "")
            resolved_plan = node.get("resolved_execution_plan") or {}
            if step_type not in {"start", "mapping", "end"}:
                return True
            if (
                node.get("asset_ref") is not None
                or node.get("asset_version_snapshot_ref") is not None
                or resolved_plan.get("asset_ref") is not None
            ):
                return True
        return False

    def _build_input_schema_draft(self, objective: str | None) -> dict[str, Any]:
        """生成当前阶段可稳定返回的最小输入草案。"""

        description = self._normalize_text(objective) or "待用户继续补充输入约束"
        return {
            "type": "object",
            "title": "探索态输入草案",
            "description": description,
            "properties": {},
            "required": [],
        }

    def _build_assistant_summary(self, pending_issues: list[dict[str, Any]]) -> str:
        """为前台生成一段确定性的系统摘要。"""

        issue_types = [
            str(item.get("issue_type") or "").strip()
            for item in pending_issues
            if isinstance(item, dict)
        ]
        ordered_issue_types = list(dict.fromkeys([item for item in issue_types if item]))
        issue_labels = [self._issue_label(issue_type) for issue_type in ordered_issue_types]

        if issue_labels:
            issues_text = "、".join(issue_labels)
            return (
                "已根据当前聊天内容生成初版 FlowDraft。"
                f"当前仍需确认：{issues_text}。"
                "建议继续补充目标范围、可用资产和关键输入参数。"
            )

        return "已根据当前聊天内容生成初版 FlowDraft，当前草稿已具备继续进入下一步处理的最小结构。"

    def _build_title(self, message: str) -> str:
        """从最新用户消息中生成一个稳定且简短的标题。"""

        normalized = self._normalize_text(message) or "新建探索会话"
        separators = ["\n", "。", ".", "！", "!", "？", "?", "；", ";", "，", ","]
        for separator in separators:
            if separator in normalized:
                normalized = normalized.split(separator, 1)[0].strip()
                break
        return normalized[:48] or "新建探索会话"

    def _build_objective(self, transcript: list[str]) -> str:
        """把多轮用户输入压成当前阶段可读的目标摘要。"""

        normalized_messages = [self._normalize_text(item) for item in transcript]
        chunks = [item for item in normalized_messages if item]
        if not chunks:
            return "待用户补充目标"

        # 先保留最近几轮补充，避免目标摘要在早期就被无限拉长。
        objective = "；".join(chunks[-3:])
        return objective[:300]

    def _derive_status(self, preflight_summary: dict[str, Any]) -> str:
        """根据预检结果回写当前草稿状态。"""

        if preflight_summary.get("is_runnable", False):
            return FlowDraftStatus.READY_FOR_TRIAL.value
        return FlowDraftStatus.NEEDS_RESOLUTION.value

    def _serialize_conversation(self, task: Task, flowdraft: DMFlowDraft) -> dict[str, Any]:
        """把会话宿主和当前草稿压平成 API 可读结构。"""

        return {
            "conversation_id": int(task.id),
            "task_id": int(task.id),
            "flowdraft_id": int(flowdraft.id),
            "title": flowdraft.title or task.title or "新建探索会话",
            "objective": flowdraft.objective,
            "flowdraft_status": flowdraft.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    def _normalize_text(self, value: str | None) -> str | None:
        """统一做最小文本归一化，避免空白消息和标题污染。"""

        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    def _issue_label(self, issue_type: str) -> str:
        """把 issue_type 转成前台摘要里更可读的中文。"""

        labels = {
            "route_pending": "技术路线",
            "asset_pending": "执行资产",
            "param_pending": "关键参数",
            "mapping_incomplete": "输出映射",
            "resolution_missing": "执行方案",
            "dependency_incomplete": "依赖关系",
            "governance_blocked": "治理规则",
        }
        return labels.get(issue_type, issue_type)

    def _flowdraft_service(self) -> FlowDraftService:
        """返回当前会话服务复用的 FlowDraftService 实例。"""

        if self.flowdraft_service is None:
            self.flowdraft_service = FlowDraftService(
                db=self.db,
                snapshot_service=self._snapshot_service(),
            )
        return self.flowdraft_service

    def _snapshot_service(self) -> SnapshotService:
        """返回当前会话服务复用的 SnapshotService 实例。"""

        if self.snapshot_service is None:
            self.snapshot_service = SnapshotService(db=self.db)
        return self.snapshot_service
