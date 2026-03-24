from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMTaskRunLink(Base):  # type: ignore
    """Bridges exploration tasks to execution runs."""

    __tablename__ = "dm_task_run_links"
    __table_args__ = (
        UniqueConstraint("task_id", "run_id", name="uq_dm_task_run_link"),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id = Column(
        Integer, ForeignKey("dm_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type = Column(String(50), nullable=False, default="trial")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task")
    run = relationship("DMRun")

    def __repr__(self) -> str:
        return (
            f"<DMTaskRunLink(task_id={self.task_id}, run_id={self.run_id}, "
            f"link_type='{self.link_type}')>"
        )
