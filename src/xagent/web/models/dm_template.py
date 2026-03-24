from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMTemplate(Base):  # type: ignore
    """逻辑模板对象。

    它回答“这类事情是什么模板”，但不直接保存某一版的全部执行内容。
    具体可执行内容放在 DMTemplateRevision 中。
    """

    __tablename__ = "dm_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_short = Column(String(64), nullable=False, index=True)
    owner_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 指向当前对团队正式生效的版本。
    latest_published_revision_id = Column(
        Integer,
        ForeignKey("dm_template_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", foreign_keys=[owner_user_id])
    revisions = relationship(
        "DMTemplateRevision",
        foreign_keys="DMTemplateRevision.template_id",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="DMTemplateRevision.created_at",
    )
    latest_published_revision = relationship(
        "DMTemplateRevision",
        foreign_keys=[latest_published_revision_id],
        post_update=True,
    )

    def __repr__(self) -> str:
        return f"<DMTemplate(id={self.id}, name='{self.name}')>"


class DMTemplateRevision(Base):  # type: ignore
    """模板版本对象。

    它保存的是“可审核、可发布、可重复执行”的完整版本内容，
    是模板沉淀和正式执行的关键实体。
    """

    __tablename__ = "dm_template_revisions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer, ForeignKey("dm_templates.id", ondelete="CASCADE"), nullable=False
    )
    version_no = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    # source_run_id 用于追溯这版草稿是从哪次成功试跑沉淀出来的。
    source_run_id = Column(
        Integer, ForeignKey("dm_runs.id", ondelete="SET NULL"), nullable=True
    )
    # business_graph_snapshot 主要服务于展示、审核和 diff，不承担实际执行语义。
    business_graph_snapshot = Column(JSON, nullable=True)
    # technical_graph 是后续重复执行的主骨架。
    technical_graph = Column(JSON, nullable=False, default=dict)
    input_schema = Column(JSON, nullable=True)
    output_mapping = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    template = relationship(
        "DMTemplate", foreign_keys=[template_id], back_populates="revisions"
    )
    source_run = relationship("DMRun", foreign_keys=[source_run_id])
    creator = relationship("User", foreign_keys=[created_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    steps = relationship(
        "DMTemplateRevisionStep",
        back_populates="revision",
        cascade="all, delete-orphan",
        order_by="DMTemplateRevisionStep.id",
    )

    def __repr__(self) -> str:
        return (
            f"<DMTemplateRevision(id={self.id}, template_id={self.template_id}, "
            f"version_no={self.version_no}, status='{self.status}')>"
        )


class DMTemplateRevisionStep(Base):  # type: ignore
    """模板版本中的具体步骤。

    每个步骤都同时保留设计意图、收敛依据和最终执行方案，
    这样模板审核和后续运维排障都有稳定依据。
    """

    __tablename__ = "dm_template_revision_steps"

    id = Column(Integer, primary_key=True, index=True)
    template_revision_id = Column(
        Integer,
        ForeignKey("dm_template_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(String(128), nullable=False, index=True)
    step_type = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    depends_on = Column(JSON, nullable=False, default=list)
    # design_intent 表示这一步业务上想完成什么。
    design_intent = Column(JSON, nullable=False, default=dict)
    # resolution_rationale 记录收敛依据，默认面向审核人展示为结构化依据。
    resolution_rationale = Column(JSON, nullable=False, default=dict)
    # resolved_execution_plan 是发布后真正重复执行所依赖的具体方案。
    resolved_execution_plan = Column(JSON, nullable=False, default=dict)
    # editable_fields 用于约束模板草稿中哪些字段可直接编辑，哪些必须重收敛。
    editable_fields = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    revision = relationship("DMTemplateRevision", back_populates="steps")

    def __repr__(self) -> str:
        return (
            f"<DMTemplateRevisionStep(id={self.id}, revision_id={self.template_revision_id}, "
            f"step_id='{self.step_id}')>"
        )
