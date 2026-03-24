from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "20260324_add_datamakepool_foundations"
down_revision: Union[str, None] = "20260317_add_task_chat_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_admin_system_scopes(inspector: Inspector) -> None:
    existing_tables = inspector.get_table_names()
    if "admin_system_scopes" not in existing_tables:
        op.create_table(
            "admin_system_scopes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("system_short", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "system_short", name="uq_admin_system_scope"),
        )
        op.create_index(
            op.f("ix_admin_system_scopes_id"), "admin_system_scopes", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_admin_system_scopes_user_id"),
            "admin_system_scopes",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_admin_system_scopes_system_short"),
            "admin_system_scopes",
            ["system_short"],
            unique=False,
        )


def _create_dm_flow_drafts(inspector: Inspector) -> None:
    existing_tables = inspector.get_table_names()
    if "dm_flow_drafts" not in existing_tables:
        op.create_table(
            "dm_flow_drafts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("objective", sa.Text(), nullable=True),
            sa.Column("business_graph_payload", sa.JSON(), nullable=False),
            sa.Column("technical_graph_payload", sa.JSON(), nullable=False),
            sa.Column("pending_issues_payload", sa.JSON(), nullable=False),
            sa.Column("preflight_summary_payload", sa.JSON(), nullable=True),
            sa.Column("input_schema_draft", sa.JSON(), nullable=True),
            sa.Column("output_mapping_draft", sa.JSON(), nullable=True),
            sa.Column("latest_snapshot_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_dm_flow_drafts_id"), "dm_flow_drafts", ["id"], unique=False)

    if "dm_flow_draft_snapshots" not in existing_tables:
        op.create_table(
            "dm_flow_draft_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("flow_draft_id", sa.Integer(), nullable=False),
            sa.Column("snapshot_type", sa.String(length=50), nullable=False),
            sa.Column("business_graph_snapshot", sa.JSON(), nullable=False),
            sa.Column("technical_graph_snapshot", sa.JSON(), nullable=False),
            sa.Column("preflight_summary_snapshot", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(
                ["flow_draft_id"], ["dm_flow_drafts.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_flow_draft_snapshots_id"),
            "dm_flow_draft_snapshots",
            ["id"],
            unique=False,
        )

        with op.batch_alter_table("dm_flow_drafts", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_dm_flow_drafts_latest_snapshot_id",
                "dm_flow_draft_snapshots",
                ["latest_snapshot_id"],
                ["id"],
                ondelete="SET NULL",
            )


def _create_dm_runs(inspector: Inspector) -> None:
    existing_tables = inspector.get_table_names()
    if "dm_runs" not in existing_tables:
        op.create_table(
            "dm_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("entry_type", sa.String(length=32), nullable=False),
            sa.Column("source_task_id", sa.Integer(), nullable=True),
            sa.Column("template_id", sa.String(length=128), nullable=True),
            sa.Column("template_revision_id", sa.String(length=128), nullable=True),
            sa.Column("initiator_user_id", sa.Integer(), nullable=False),
            sa.Column("system_short", sa.String(length=64), nullable=True),
            sa.Column("objective", sa.Text(), nullable=True),
            sa.Column("input_payload", sa.JSON(), nullable=True),
            sa.Column("resolved_input", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("final_output", sa.JSON(), nullable=True),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(
                ["source_task_id"], ["tasks.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["initiator_user_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_dm_runs_id"), "dm_runs", ["id"], unique=False)
        op.create_index(
            op.f("ix_dm_runs_source_task_id"),
            "dm_runs",
            ["source_task_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_dm_runs_initiator_user_id"),
            "dm_runs",
            ["initiator_user_id"],
            unique=False,
        )

    if "dm_run_steps" not in existing_tables:
        op.create_table(
            "dm_run_steps",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("step_id", sa.String(length=128), nullable=False),
            sa.Column("step_type", sa.String(length=64), nullable=False),
            sa.Column("step_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("depends_on", sa.JSON(), nullable=False),
            sa.Column("resolved_execution_plan_snapshot", sa.JSON(), nullable=True),
            sa.Column("asset_version_snapshot_ref", sa.JSON(), nullable=True),
            sa.Column("input_snapshot", sa.JSON(), nullable=True),
            sa.Column("output_snapshot", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["run_id"], ["dm_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_run_steps_id"), "dm_run_steps", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_dm_run_steps_run_id"), "dm_run_steps", ["run_id"], unique=False
        )
        op.create_index(
            op.f("ix_dm_run_steps_step_id"), "dm_run_steps", ["step_id"], unique=False
        )


def upgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    _create_admin_system_scopes(inspector)
    inspector = Inspector.from_engine(bind)
    _create_dm_flow_drafts(inspector)
    inspector = Inspector.from_engine(bind)
    _create_dm_runs(inspector)


def downgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_run_steps" in existing_tables:
        op.drop_index(op.f("ix_dm_run_steps_step_id"), table_name="dm_run_steps")
        op.drop_index(op.f("ix_dm_run_steps_run_id"), table_name="dm_run_steps")
        op.drop_index(op.f("ix_dm_run_steps_id"), table_name="dm_run_steps")
        op.drop_table("dm_run_steps")

    if "dm_runs" in existing_tables:
        op.drop_index(op.f("ix_dm_runs_initiator_user_id"), table_name="dm_runs")
        op.drop_index(op.f("ix_dm_runs_source_task_id"), table_name="dm_runs")
        op.drop_index(op.f("ix_dm_runs_id"), table_name="dm_runs")
        op.drop_table("dm_runs")

    if "dm_flow_drafts" in existing_tables:
        with op.batch_alter_table("dm_flow_drafts", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_dm_flow_drafts_latest_snapshot_id", type_="foreignkey"
                )
            except Exception:
                pass

    if "dm_flow_draft_snapshots" in existing_tables:
        op.drop_index(
            op.f("ix_dm_flow_draft_snapshots_id"), table_name="dm_flow_draft_snapshots"
        )
        op.drop_table("dm_flow_draft_snapshots")

    if "dm_flow_drafts" in existing_tables:
        op.drop_index(op.f("ix_dm_flow_drafts_id"), table_name="dm_flow_drafts")
        op.drop_table("dm_flow_drafts")

    if "admin_system_scopes" in existing_tables:
        op.drop_index(
            op.f("ix_admin_system_scopes_system_short"),
            table_name="admin_system_scopes",
        )
        op.drop_index(
            op.f("ix_admin_system_scopes_user_id"), table_name="admin_system_scopes"
        )
        op.drop_index(op.f("ix_admin_system_scopes_id"), table_name="admin_system_scopes")
        op.drop_table("admin_system_scopes")
