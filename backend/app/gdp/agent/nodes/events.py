"""GDP Agent 业务流事件工具。

本模块负责把 Agent 图节点的"等待用户输入"状态，作为一条 ``custom`` 流事件
推送给前端。它是 GDP Agent 与前端之间的一个跨边界契约，前端依赖事件结构做
实时交互（弹确认框、追加缺失入参、审批写操作等）。

``gdp_waiting_user`` 事件契约
=============================

权威状态由 ``task_service.mark_waiting_user`` 落库；本事件是它的实时镜像，
**附加**（additive）于 LangGraph 的 ``__interrupt__`` 机制之上，不替代它。
事件发送失败会被静默吞掉（仅 debug 日志），因为客户端始终可以回查任务状态。

发往 custom stream 的事件结构：

.. code-block:: json

    {
      "type": "gdp_waiting_user",
      "taskRunId": "task_xxx",
      "phase": "SCENE_FULFILLMENT",
      "questionType": "SCENE_CANDIDATE_CONFIRM",
      "question": "面向用户的问题文案。",
      "details": { "...": "随 questionType 变化，见下表" },
      "message": "与落库 message 一致的简短说明。"
    }

字段说明：

- ``type``：恒为 ``"gdp_waiting_user"``，前端据此过滤本类事件。
- ``taskRunId``：所属造数任务运行 ID，用于关联任务上下文。
- ``phase``：发出事件时所处的 ``DatagenTaskPhase``。注意这是**当前**阶段
  （``WAITING_USER`` 前的业务阶段），并非恢复阶段；恢复阶段由落库 payload 里的
  ``resumePhase``（部分分支提供）或 ``human_confirm`` 按 ``questionType`` 推断。
- ``questionType``：稳定的枚举字符串，决定 ``details`` 的形状和前端交互方式（见下）。
- ``question``：面向用户的问题文案，可直接展示。
- ``details``：随 ``questionType`` 变化的结构化上下文；缺省时为 ``{}``。
- ``message``：与 ``mark_waiting_user`` 落库 message 一致的简短说明。

``questionType`` 取值与 ``details`` 契约
----------------------------------------

================================  ==============================  ============================================================
questionType                      来源节点                          details 关键字段
================================  ==============================  ============================================================
``SCENE_CANDIDATE_CONFIRM``       scene_fulfillment               ``candidates``、``recommended``、``confirmationReason``
``SCENE_INPUT_REQUIRED``          scene_fulfillment               ``sceneCode``、``missingInputs``（list[str]）
``WRITE_SCENE_APPROVAL``          scene_fulfillment               ``sceneCode``、``envCode``、``sideEffects``
``SOURCE_CANDIDATE_CONFIRM``      scene_design                    ``candidates``、``recommended``、``confirmationReason``
``SOURCE_INPUT_REQUIRED``         scene_design                    ``sourceCode``、``sourceType``、``missingInputs``（list[str]）
``SOURCE_CONFIG_REQUIRED``        source_config                   ``goal``、``envCode``、``expectedPayload``
``SOURCE_CONFIG_INVALID``         source_config                   ``errors``（Pydantic）、``received``
``INFRA_CONFIG_REQUIRED``         infra_config                    ``goal``、``envCode``、``basis``、``expectedPayload``
``INFRA_CONFIG_INVALID``          infra_config                    ``errors``（Pydantic）、``received``
================================  ==============================  ============================================================

新增分支时，请同步更新本表，并保持 ``questionType`` 的前缀约定
（``human_confirm`` 用 ``startswith("SOURCE_CONFIG")`` / ``"INFRA_CONFIG"`` 推断恢复阶段）。

安全提示
--------

``*_INVALID`` 分支的 ``details.received`` 是用户/Agent 提交的原始 payload，会
随本事件流向前端。若该 payload 可能携带凭据（数据源连接串、HTTP Source 的认证
信息等），调用方应在放入 ``pending`` 之前完成脱敏，避免敏感值经实时流泄露。
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.config import get_stream_writer

from app.gdp.datagen.redaction import redact_sensitive_payload

logger = logging.getLogger(__name__)


def emit_waiting_user_event(payload: dict[str, Any], *, message: str) -> None:
    """向 DeerFlow custom stream 发送一条 ``gdp_waiting_user`` 事件。

    从节点构造的 ``pending`` 字典中读取 ``taskRunId`` / ``phase`` /
    ``questionType`` / ``question`` / ``details`` 字段，组装为统一事件结构后
    写入 LangGraph custom stream。完整事件契约见模块级文档。

    Args:
        payload: 节点构造的 ``pending`` 中断字典。缺失字段以 ``None`` /
            ``{}`` 兜底，因此结构不完整也不会抛错。
        message: 简短说明，与对应 ``mark_waiting_user`` 落库 message 保持一致。

    Note:
        本函数为"尽力而为"：在非流式上下文调用、或 writer 不可用时会静默失败
        （仅记录 debug 日志），绝不打断图节点的状态流转。权威状态已由
        ``mark_waiting_user`` 先行落库，事件丢失可由客户端回查恢复。
    """

    try:
        payload = redact_sensitive_payload(payload)
        writer = get_stream_writer()
        writer(
            {
                "type": "gdp_waiting_user",
                "taskRunId": payload.get("taskRunId"),
                "phase": payload.get("phase"),
                "questionType": payload.get("questionType"),
                "question": payload.get("question"),
                "details": payload.get("details") or {},
                "message": message,
            }
        )
    except Exception:  # noqa: BLE001
        logger.debug("发送 GDP 等待用户事件失败，已跳过。", exc_info=True)
