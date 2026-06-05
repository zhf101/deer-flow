"""GDP 造数执行引擎 Pydantic 数据模型。

定义执行请求（ExecutionRequest）、步骤结果（StepResult）和整体执行结果（ExecutionResult）。
这些模型描述的是运行时状态，与 models.py 中的设计时配置模型不同。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.gdp.models import StepType


# 单个步骤的执行结果——记录每一步的耗时、输出、原始响应和错误信息
class StepResult(BaseModel):
    stepId: str                                        # 步骤标识
    stepName: str | None = None                        # 步骤名称
    type: StepType                                     # 步骤类型
    status: Literal["SUCCESS", "FAILED", "SKIPPED"]   # 执行状态
    startedAt: datetime                                # 开始时间
    finishedAt: datetime                               # 结束时间
    durationMs: int                                    # 耗时（毫秒）
    outputs: dict[str, Any] = Field(default_factory=dict)  # outputMapping 提取的输出
    rawResponse: Any = None                            # 原始响应（HTTP body / SQL result）
    error: str | None = None                           # 错误信息（失败时有值）
    statusCode: int | None = None                      # HTTP 状态码（仅 HTTP 步骤）


# 整个场景的执行结果——汇总所有步骤结果和最终输出
class ExecutionResult(BaseModel):
    sceneCode: str                                          # 场景编码
    versionNo: int                                          # 执行的版本号
    envCode: str                                            # 执行的环境编码
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]        # 整体状态
    startedAt: datetime                                     # 执行开始时间
    finishedAt: datetime                                    # 执行结束时间
    durationMs: int                                         # 总耗时（毫秒）
    stepResults: list[StepResult] = Field(default_factory=list)  # 各步骤结果列表
    finalOutput: dict[str, Any] = Field(default_factory=dict)    # resultMapping 解析后的最终输出
    errors: list[str] = Field(default_factory=list)              # 收集的错误信息


# 执行请求——客户端提交的执行参数
class ExecutionRequest(BaseModel):
    envCode: str = Field(..., min_length=1, description="环境编码，如 'DEV'、'SIT'")
    inputs: dict[str, Any] = Field(default_factory=dict, description="输入参数键值对")
