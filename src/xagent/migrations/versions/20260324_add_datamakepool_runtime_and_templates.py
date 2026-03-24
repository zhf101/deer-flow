from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "20260324_add_datamakepool_runtime_and_templates"
down_revision: Union[str, None] = "20260324_add_datamakepool_foundations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_templates" not in existing_tables:
        op.create_table(
            "dm_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("system_short", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=False),
            sa.Column("latest_published_revision_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_dm_templates_id"), "dm_templates", ["id"], unique=False)

    if "dm_template_revisions" not in existing_tables:
        op.create_table(
            "dm_template_revisions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("source_run_id", sa.Integer(), nullable=True),
            sa.Column("business_graph_snapshot", sa.JSON(), nullable=True),
            sa.Column("technical_graph", sa.JSON(), nullable=False),
            sa.Column("input_schema", sa.JSON(), nullable=True),
            sa.Column("output_mapping", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["template_id"], ["dm_templates.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["source_run_id"], ["dm_runs.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_template_revisions_id"),
            "dm_template_revisions",
            ["id"],
            unique=False,
        )

        with op.batch_alter_table("dm_templates", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_dm_templates_latest_published_revision_id",
                "dm_template_revisions",
                ["latest_published_revision_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if "dm_template_revision_steps" not in existing_tables:
        op.create_table(
            "dm_template_revision_steps",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("template_revision_id", sa.Integer(), nullable=False),
            sa.Column("step_id", sa.String(length=128), nullable=False),
            sa.Column("step_type", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("depends_on", sa.JSON(), nullable=False),
            sa.Column("design_intent", sa.JSON(), nullable=False),
            sa.Column("resolution_rationale", sa.JSON(), nullable=False),
            sa.Column("resolved_execution_plan", sa.JSON(), nullable=False),
            sa.Column("editable_fields", sa.JSON(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(
                ["template_revision_id"],
                ["dm_template_revisions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_template_revision_steps_id"),
            "dm_template_revision_steps",
            ["id"],
            unique=False,
        )

    if "dm_audit_records" not in existing_tables:
        op.create_table(
            "dm_audit_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("run_step_id", sa.Integer(), nullable=True),
            sa.Column("actor_user_id", sa.Integer(), nullable=False),
            sa.Column("system_short", sa.String(length=64), nullable=True),
            sa.Column("audit_type", sa.String(length=50), nullable=False),
            sa.Column("risk_level", sa.String(length=32), nullable=True),
            sa.Column("confirmation_mode", sa.String(length=50), nullable=True),
            sa.Column("confirmed_by", sa.Integer(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("target_objects", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["run_id"], ["dm_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_step_id"], ["dm_run_steps.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_audit_records_id"), "dm_audit_records", ["id"], unique=False
        )

    if "dm_task_run_links" not in existing_tables:
        op.create_table(
            "dm_task_run_links",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("link_type", sa.String(length=50), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["dm_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", "run_id", name="uq_dm_task_run_link"),
        )
        op.create_index(
            op.f("ix_dm_task_run_links_id"), "dm_task_run_links", ["id"], unique=False
        )


def downgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_task_run_links" in existing_tables:
        op.drop_index(op.f("ix_dm_task_run_links_id"), table_name="dm_task_run_links")
        op.drop_table("dm_task_run_links")

    if "dm_audit_records" in existing_tables:
        op.drop_index(op.f("ix_dm_audit_records_id"), table_name="dm_audit_records")
        op.drop_table("dm_audit_records")

    if "dm_template_revision_steps" in existing_tables:
        op.drop_index(
            op.f("ix_dm_template_revision_steps_id"),
            table_name="dm_template_revision_steps",
        )
        op.drop_table("dm_template_revision_steps")

    if "dm_templates" in existing_tables:
        with op.batch_alter_table("dm_templates", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_dm_templates_latest_published_revision_id", type_="foreignkey"
                )
            except Exception:
                pass

    if "dm_template_revisions" in existing_tables:
        op.drop_index(
            op.f("ix_dm_template_revisions_id"),
            table_name="dm_template_revisions",
        )
        op.drop_table("dm_template_revisions")

    if "dm_templates" in existing_tables:
        op.drop_index(op.f("ix_dm_templates_id"), table_name="dm_templates")
        op.drop_table("dm_templates")
