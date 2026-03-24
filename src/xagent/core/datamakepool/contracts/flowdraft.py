from enum import Enum


class FlowDraftStatus(str, Enum):
    """FlowDraft 在探索态和试跑态之间的关键状态。"""

    DRAFT = "draft"
    NEEDS_RESOLUTION = "needs_resolution"
    READY_FOR_TRIAL = "ready_for_trial"
    TRIAL_RUNNING = "trial_running"
    TRIAL_FAILED = "trial_failed"
    TRIAL_SUCCEEDED = "trial_succeeded"


class StepType(str, Enum):
    """V1 技术图允许出现的步骤类型。"""

    HTTP = "http_step"
    SQL = "sql_step"
    CONFIRM = "confirm"
    MAPPING = "mapping"
    START = "start"
    END = "end"
