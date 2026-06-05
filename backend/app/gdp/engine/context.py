"""GDP 执行上下文——存储变量、步骤输出、系统变量等运行时状态。

上下文是一个可变的普通 Python 类（非 Pydantic），在整个场景执行过程中
作为"数据总线"贯穿所有步骤执行器，负责：
- 保存用户输入参数（${input.xxx}）
- 保存各步骤的输出结果（${steps.stepId.outputs.xxx}）
- 保存 TRANSFORM 步骤写入的变量（${vars.xxx}）
- 提供系统变量（${system.now}、${system.uuid} 等）
- 保存预加载的服务端点和数据源配置
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


class ExecutionContext:
    """场景执行上下文，贯穿整个执行生命周期。"""

    def __init__(self, inputs: dict[str, Any], env_code: str) -> None:
        # ── 用户输入参数（${input.xxx}）──
        self.inputs: dict[str, Any] = dict(inputs)

        # ── TRANSFORM 写入的变量（${vars.xxx}）──
        self.vars: dict[str, Any] = {}

        # ── 各步骤 outputMapping 提取的输出（${steps.stepId.outputs.xxx}）──
        self.step_outputs: dict[str, dict[str, Any]] = {}

        # ── 各步骤的原始响应（用于 errorMapping 等场景）──
        self.step_raw: dict[str, Any] = {}

        # ── 环境编码（${env.xxx} 解析时需要）──
        self.env_code: str = env_code

        # ── 预加载的服务端点（serviceCode → baseUrl）──
        self.service_endpoints: dict[str, str] = {}

        # ── 预加载的数据源配置（datasourceCode → DatasourceConfig 对象）──
        self.datasources: dict[str, Any] = {}

        # ── 执行过程中收集的错误列表──
        self.errors: list[str] = []

    def set_step_output(self, step_id: str, outputs: dict[str, Any]) -> None:
        """保存某个步骤的 outputMapping 提取结果。"""
        self.step_outputs[step_id] = outputs

    def set_step_raw(self, step_id: str, raw: Any) -> None:
        """保存某个步骤的原始响应（HTTP 结构化数据 / SQL 执行结果）。"""
        self.step_raw[step_id] = raw

    def set_var(self, name: str, value: Any) -> None:
        """保存 TRANSFORM 步骤写入的变量，支持 'vars.xxx' 格式（自动去掉前缀）。"""
        key = name.removeprefix("vars.") if name.startswith("vars.") else name
        self.vars[key] = value

    def get_system_var(self, name: str) -> Any:
        """获取系统变量。

        支持的变量：
        - system.now → ISO 8601 格式的当前时间
        - system.uuid → 随机 UUID
        - system.timestamp → 毫秒级 Unix 时间戳
        """
        if name == "now":
            return datetime.now(UTC).isoformat()
        if name == "uuid":
            return str(uuid.uuid4())
        if name == "timestamp":
            return int(datetime.now(UTC).timestamp() * 1000)
        return None
