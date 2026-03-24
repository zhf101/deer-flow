from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMFlowDraft(Base):  # type: ignore
    """Exploration-stage business DAG draft rooted in a task conversation."""

    __tablename__ = "dm_flow_drafts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    title = Column(String(255), nullable=True)
    objective = Column(Text, nullable=True)
    business_graph_payload = Column(JSON, nullable=False, default=dict)
    technical_graph_payload = Column(JSON, nullable=False, default=dict)
    pending_issues_payload = Column(JSON, nullable=False, default=list)
    preflight_summary_payload = Column(JSON, nullable=True)
    input_schema_draft = Column(JSON, nullable=True)
    output_mapping_draft = Column(JSON, nullable=True)
    latest_snapshot_id = Column(
        Integer,
        ForeignKey("dm_flow_draft_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task = relationship("Task", back_populates="dm_flow_drafts")
    creator = relationship("User", foreign_keys=[created_by])
    snapshots = relationship(
        "DMFlowDraftSnapshot",
        foreign_keys="DMFlowDraftSnapshot.flow_draft_id",
        back_populates="flow_draft",
        cascade="all, delete-orphan",
        order_by="DMFlowDraftSnapshot.created_at",
    )
    latest_snapshot = relationship(
        "DMFlowDraftSnapshot", foreign_keys=[latest_snapshot_id], post_update=True
    )

    def __repr__(self) -> str:
        return f"<DMFlowDraft(id={self.id}, task_id={self.task_id}, status='{self.status}')>"


class DMFlowDraftSnapshot(Base):  # type: ignore
    """Versioned snapshot for important FlowDraft milestones."""

    __tablename__ = "dm_flow_draft_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    flow_draft_id = Column(
        Integer, ForeignKey("dm_flow_drafts.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_type = Column(String(50), nullable=False)
    business_graph_snapshot = Column(JSON, nullable=False, default=dict)
    technical_graph_snapshot = Column(JSON, nullable=False, default=dict)
    preflight_summary_snapshot = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    flow_draft = relationship(
        "DMFlowDraft", foreign_keys=[flow_draft_id], back_populates="snapshots"
    )
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return (
            f"<DMFlowDraftSnapshot(id={self.id}, flow_draft_id={self.flow_draft_id}, "
            f"type='{self.snapshot_type}')>"
        )
