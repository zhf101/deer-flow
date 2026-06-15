"""领域对象身份标识类型。"""

from __future__ import annotations

# 每个标识符对应运行时中一类核心实体，用于全链路追踪和审计。
TaskRunId = str       # 一次造数任务的唯一标识
StepId = str          # 造数目标拆解出的业务步骤标识
ActionId = str        # 系统为满足用户需求而执行的动作标识
AttemptId = str       # 动作的每次执行尝试标识（支持重试）
VariableId = str      # 造数过程中产出或消费的业务数据标识
EvidenceId = str      # 判定造数是否成功的证据链标识
VerdictId = str       # 最终判定结论标识
StorageRef = str      # 敏感或大体积数据的安全存储引用（避免明文落库）
HashValue = str       # 数据完整性校验哈希

