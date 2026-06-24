"""用户恢复暂停任务的命令体系。

用户的造数任务在运行中可能因需要人工决策而暂停（WAITING_USER），此时前端
会向用户展示待处理事项（如选择场景、补充入参、审批确认等）。用户做出回复后，
前端将回复类型和参数发送到 API，API 层调用本模块的 parse_runtime_command
将用户意图转为内部命令对象，交由编排引擎恢复任务执行。

每种命令对应一种用户回复场景：
- ApproveCommand：用户批准系统选定的场景
- SupplyInputCommand：用户补充系统提示的缺失入参
- ConfirmUnknownStateCommand：用户确认执行结果未知并选择停止
- SelectSceneCommand：用户在候选列表中选择一个场景
- SupplySceneCodeCommand：系统搜不到候选时用户手动输入场景编码
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..models import ReplyType
from ..support.errors import RuntimeValidationError


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


@dataclass(frozen=True)
class AcceptContractDriftCommand(RuntimeCommand):
    """接受执行前重验得到的新场景契约，按新契约继续执行。"""


def parse_runtime_command(reply_type: ReplyType | str, payload: Mapping[str, Any] | None) -> RuntimeCommand:
    """将用户在前端的回复转化为编排引擎可执行的内部命令。

    业务目标：桥接用户操作与系统执行——用户在前端做出回复（如批准、补参、选场景）后，
    本函数将前端传来的 reply_type 和 payload 解析为类型安全的命令对象。
    当前动作：校验 reply_type 合法性，按类型分发到对应的 Command 构造器。
    预期结果：返回具体的 RuntimeCommand 子类实例，编排引擎据此恢复暂停的造数任务。
    """

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
        ReplyType.ACCEPT_CONTRACT_DRIFT: AcceptContractDriftCommand,
    }
    return command_map[normalized](command_payload)
