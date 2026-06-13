"""GDP Agent Runtime 恢复命令。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import RuntimeValidationError
from .models import ReplyType


@dataclass(frozen=True)
class RuntimeCommand:
    """恢复 WAITING_USER 任务的命令基类。"""

    payload: dict[str, Any]


@dataclass(frozen=True)
class ApproveCommand(RuntimeCommand):
    """批准已选定且待审批的场景。"""


@dataclass(frozen=True)
class SupplyInputCommand(RuntimeCommand):
    """补充缺失输入。"""


@dataclass(frozen=True)
class ConfirmUnknownStateCommand(RuntimeCommand):
    """确认执行结果未知并停止任务，避免重放写请求。"""


@dataclass(frozen=True)
class SelectSceneCommand(RuntimeCommand):
    """在候选场景中选择一个场景。"""


@dataclass(frozen=True)
class SupplySceneCodeCommand(RuntimeCommand):
    """零候选时手动补充 scene_code。"""


def parse_runtime_command(reply_type: ReplyType | str, payload: Mapping[str, Any] | None) -> RuntimeCommand:
    """把 API reply_type 解析成内部命令对象。"""

    try:
        normalized = reply_type if isinstance(reply_type, ReplyType) else ReplyType(str(reply_type))
    except ValueError as exc:
        raise RuntimeValidationError(f"不支持的 reply_type: {reply_type}") from exc

    command_payload = dict(payload or {})
    command_map: dict[ReplyType, type[RuntimeCommand]] = {
        ReplyType.APPROVE: ApproveCommand,
        ReplyType.SUPPLY_INPUT: SupplyInputCommand,
        ReplyType.CONFIRM_UNKNOWN_STATE: ConfirmUnknownStateCommand,
        ReplyType.SELECT_SCENE: SelectSceneCommand,
        ReplyType.SUPPLY_SCENE_CODE: SupplySceneCodeCommand,
    }
    return command_map[normalized](command_payload)
