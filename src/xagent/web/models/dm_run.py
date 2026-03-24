from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMRun(Base):  # type: ignore
    """Execution-stage root object for trials and template runs."""

    __tablename__ = "dm_runs"

    id = Column(Integer, primary_key=True, index=True)
    entry_type = Column(String(32), nullable=False)
    source_task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id = Column(String(128), nullable=True, index=True)
    template_revision_id = Column(String(128), nullable=True, index=True)
    initiator_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
    """Execution snapshot for a single technical step within a run."""

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
    resolved_execution_plan_snapshot = Column(JSON, nullable=True)
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
