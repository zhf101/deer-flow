from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMAuditRecord(Base):  # type: ignore
    """Execution governance and SQL audit record."""

    __tablename__ = "dm_audit_records"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("dm_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_step_id = Column(
        Integer,
        ForeignKey("dm_run_steps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    system_short = Column(String(64), nullable=True, index=True)
    audit_type = Column(String(50), nullable=False, default="sql_execution")
    risk_level = Column(String(32), nullable=True)
    confirmation_mode = Column(String(50), nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    target_objects = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="created")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    run = relationship("DMRun")
    run_step = relationship("DMRunStep")
    actor = relationship("User", foreign_keys=[actor_user_id])
    confirmer = relationship("User", foreign_keys=[confirmed_by])

    def __repr__(self) -> str:
        return (
            f"<DMAuditRecord(id={self.id}, run_id={self.run_id}, "
            f"audit_type='{self.audit_type}', status='{self.status}')>"
        )
