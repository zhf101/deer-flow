from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMRun(Base):  # type: ignore
    """执行态根对象。

    它承载的是某次 trial 或某次模板正式执行，
    与探索态 Task 分层存在，不再混用同一宿主语义。
    """

    __tablename__ = "dm_runs"

    id = Column(Integer, primary_key=True, index=True)
    # entry_type 用于区分 run 来源，如 chat trial 或 template execute。
    entry_type = Column(String(32), nullable=False)
    source_task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id = Column(String(128), nullable=True, index=True)
    template_revision_id = Column(String(128), nullable=True, index=True)
    initiator_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # system_short 参与权限过滤和审核归属判断。
    system_short = Column(String(64), nullable=True, index=True)
    objective = Column(Text, nullable=True)
    input_payload = Column(JSON, nullable=True)
    resolved_input = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    final_output = Column(JSON, nullable=True)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_task = relationship("Task", back_populates="dm_runs")
    initiator = relationship("User", foreign_keys=[initiator_user_id])
    steps = relationship(
        "DMRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DMRunStep.id",
    )

    def __repr__(self) -> str:
        return (
            f"<DMRun(id={self.id}, entry_type='{self.entry_type}', "
            f"status='{self.status}')>"
        )


class DMRunStep(Base):  # type: ignore
    """Run 内单个技术步骤的执行快照。

    这里保存的是“这一次实际怎么跑的”，不是设计意图。
    """

    __tablename__ = "dm_run_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("dm_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id = Column(String(128), nullable=False, index=True)
    step_type = Column(String(64), nullable=False)
    step_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    depends_on = Column(JSON, nullable=False, default=list)
    # 固化本次执行时真正使用的执行方案，避免后续设计变化污染历史回放。
    resolved_execution_plan_snapshot = Column(JSON, nullable=True)
    # 对需要锁版本的资产，记录本次执行所绑定的版本快照引用。
    asset_version_snapshot_ref = Column(JSON, nullable=True)
    input_snapshot = Column(JSON, nullable=True)
    output_snapshot = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("DMRun", back_populates="steps")

    def __repr__(self) -> str:
        return (
            f"<DMRunStep(id={self.id}, run_id={self.run_id}, "
            f"step_id='{self.step_id}', status='{self.status}')>"
        )
