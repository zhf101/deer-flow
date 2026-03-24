from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from xagent.web.models.dm_run import DMRun
from xagent.web.models.dm_template import (
    DMTemplate,
    DMTemplateRevision,
    DMTemplateRevisionStep,
)

@dataclass
class TemplateService:
    """模板服务。

    当前第一版先打通“从成功 Run 生成模板草稿版本”的最小闭环。
    """

    db: Session

    def create_revision_from_run(
        self,
        run_id: int,
        template_name: Optional[str] = None,
        description: Optional[str] = None,
        system_short: Optional[str] = None,
        template_id: Optional[int] = None,
        business_graph_snapshot: Optional[dict[str, Any]] = None,
        technical_graph: Optional[dict[str, Any]] = None,
        input_schema: Optional[dict[str, Any]] = None,
        output_mapping: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """从一条成功 Run 生成模板草稿版本。

        当前策略：
        - 如果未指定 template_id，则创建新的逻辑模板
        - 如果指定了 template_id，则在现有模板下生成新草稿版本
        - 优先使用外部传入的 technical_graph；如果没有，则从 RunStep 最小重建
        """
        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        try:
            template = self._get_or_create_template(
                run=run,
                template_id=template_id,
                template_name=template_name,
                description=description,
                system_short=system_short,
            )
            version_no = self._next_version_no(template.id)
            resolved_technical_graph = technical_graph or self._rebuild_technical_graph(run)

            revision = DMTemplateRevision(
                template_id=template.id,
                version_no=version_no,
                status="draft",
                source_run_id=run.id,
                business_graph_snapshot=business_graph_snapshot,
                technical_graph=resolved_technical_graph,
                input_schema=input_schema,
                output_mapping=output_mapping,
                created_by=run.initiator_user_id,
            )
            self.db.add(revision)
            self.db.flush()

            self._create_revision_steps(revision.id, run, resolved_technical_graph)
            self.db.commit()

            return {
                "template_id": template.id,
                "revision_id": revision.id,
                "version_no": revision.version_no,
                "status": revision.status,
                "source_run_id": run.id,
            }
        except Exception:
            self.db.rollback()
            raise

    def submit_review(self, revision_id: int) -> dict[str, Any]:
        """提交模板版本审核。"""
        revision = (
            self.db.query(DMTemplateRevision)
            .filter(DMTemplateRevision.id == revision_id)
            .first()
        )
        if revision is None:
            raise ValueError(f"Template revision {revision_id} not found")

        revision.status = "pending_review"
        self.db.commit()
        return {"revision_id": revision.id, "status": revision.status}

    def approve_revision(self, revision_id: int, reviewer_user_id: int) -> dict[str, Any]:
        """审批通过模板版本，并切换逻辑模板的当前发布版本。"""
        revision = (
            self.db.query(DMTemplateRevision)
            .filter(DMTemplateRevision.id == revision_id)
            .first()
        )
        if revision is None:
            raise ValueError(f"Template revision {revision_id} not found")

        template = revision.template
        if template is None:
            raise ValueError(f"Template {revision.template_id} not found")

        try:
            revision.status = "published"
            revision.reviewed_by = reviewer_user_id
            template.latest_published_revision_id = revision.id
            self.db.commit()
            return {"revision_id": revision.id, "status": revision.status}
        except Exception:
            self.db.rollback()
            raise

    def list_templates(self) -> list[dict[str, Any]]:
        """列出模板逻辑对象。"""
        templates = self.db.query(DMTemplate).order_by(DMTemplate.created_at.desc()).all()
        return [self._serialize_template(template) for template in templates]

    def list_revisions(self, template_id: int) -> list[dict[str, Any]]:
        """列出指定模板的全部版本。"""
        template = self.db.query(DMTemplate).filter(DMTemplate.id == template_id).first()
        if template is None:
            raise ValueError(f"Template {template_id} not found")
        return [self._serialize_revision(revision) for revision in template.revisions]

    def _get_or_create_template(
        self,
        run: DMRun,
        template_id: Optional[int],
        template_name: Optional[str],
        description: Optional[str],
        system_short: Optional[str],
    ) -> DMTemplate:
        """获取现有模板，或基于 Run 创建新的逻辑模板。"""
        if template_id is not None:
            template = self.db.query(DMTemplate).filter(DMTemplate.id == template_id).first()
            if template is None:
                raise ValueError(f"Template {template_id} not found")
            return template

        template = DMTemplate(
            name=template_name or self._default_template_name(run),
            description=description or run.objective,
            system_short=system_short or run.system_short or "default",
            owner_user_id=run.initiator_user_id,
        )
        self.db.add(template)
        self.db.flush()
        return template

    def _next_version_no(self, template_id: int) -> int:
        """计算模板的下一个版本号。"""
        current = (
            self.db.query(func.max(DMTemplateRevision.version_no))
            .filter(DMTemplateRevision.template_id == template_id)
            .scalar()
        )
        return int(current or 0) + 1

    def _default_template_name(self, run: DMRun) -> str:
        """为未命名模板生成一个可读默认名。"""
        objective = (run.objective or "").strip()
        if objective:
            return objective[:80]
        return f"Run {run.id} generated template"

    def _rebuild_technical_graph(self, run: DMRun) -> dict[str, Any]:
        """从 RunStep 最小重建技术图。

        这是一个兜底路径。为了避免模板沉淀被阻塞，如果调用方还没有传
        完整 technical_graph，就先按 RunStep 快照重建最小结构。
        """
        nodes: list[dict[str, Any]] = []
        for step in run.steps:
            nodes.append(
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "name": step.step_name,
                    "depends_on": step.depends_on or [],
                    "resolved_execution_plan": step.resolved_execution_plan_snapshot or {},
                }
            )
        return {"nodes": nodes}

    def _create_revision_steps(
        self, revision_id: int, run: DMRun, technical_graph: dict[str, Any]
    ) -> None:
        """根据 technical_graph 和 RunStep 快照生成模板步骤。

        当前优先使用 technical_graph 中的结构；如果缺字段，则再从对应 RunStep 补足。
        """
        step_map = {step.step_id: step for step in run.steps}
        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []

        for node in nodes:
            if not isinstance(node, dict):
                continue

            step_id = str(node.get("step_id") or node.get("id") or "")
            run_step = step_map.get(step_id)

            revision_step = DMTemplateRevisionStep(
                template_revision_id=revision_id,
                step_id=step_id,
                step_type=str(node.get("step_type") or (run_step.step_type if run_step else "")),
                name=str(node.get("name") or (run_step.step_name if run_step else "Unnamed Step")),
                depends_on=node.get("depends_on") or (run_step.depends_on if run_step else []),
                design_intent=node.get("design_intent") or {},
                resolution_rationale=node.get("resolution_rationale") or {},
                resolved_execution_plan=(
                    node.get("resolved_execution_plan")
                    or (run_step.resolved_execution_plan_snapshot if run_step else {})
                    or {}
                ),
                editable_fields=node.get("editable_fields") or [],
            )
            self.db.add(revision_step)

    def _serialize_template(self, template: DMTemplate) -> dict[str, Any]:
        """将模板对象压平成 API 结构。"""
        return {
            "template_id": template.id,
            "name": template.name,
            "description": template.description,
            "system_short": template.system_short,
            "owner_user_id": template.owner_user_id,
            "latest_published_revision_id": template.latest_published_revision_id,
            "revisions_count": len(template.revisions),
        }

    def _serialize_revision(self, revision: DMTemplateRevision) -> dict[str, Any]:
        """将模板版本对象压平成 API 结构。"""
        return {
            "revision_id": revision.id,
            "template_id": revision.template_id,
            "version_no": revision.version_no,
            "status": revision.status,
            "source_run_id": revision.source_run_id,
            "created_by": revision.created_by,
            "reviewed_by": revision.reviewed_by,
            "review_comment": revision.review_comment,
            "steps_count": len(revision.steps),
        }
