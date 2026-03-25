from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "20260325_add_datamakepool_assets"
down_revision: Union[str, None] = "20260324_add_datamakepool_runtime_and_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_http_assets" not in existing_tables:
        op.create_table(
            "dm_http_assets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("system_short", sa.String(length=64), nullable=False),
            sa.Column("base_url", sa.String(length=1024), nullable=False),
            sa.Column("method", sa.String(length=16), nullable=False),
            sa.Column("path_template", sa.String(length=1024), nullable=False),
            sa.Column("query_template", sa.JSON(), nullable=True),
            sa.Column("headers_template", sa.JSON(), nullable=True),
            sa.Column("body_template", sa.JSON(), nullable=True),
            sa.Column("request_schema", sa.JSON(), nullable=True),
            sa.Column("auth_type", sa.String(length=64), nullable=True),
            sa.Column("auth_config_ciphertext", sa.Text(), nullable=True),
            sa.Column("response_extraction_rules", sa.JSON(), nullable=True),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False),
            sa.Column("max_response_bytes", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_http_assets_id"), "dm_http_assets", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_dm_http_assets_owner_user_id"),
            "dm_http_assets",
            ["owner_user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_dm_http_assets_system_short"),
            "dm_http_assets",
            ["system_short"],
            unique=False,
        )

    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_sql_assets" not in existing_tables:
        op.create_table(
            "dm_sql_assets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("system_short", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=False),
            sa.Column("current_active_version_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_dm_sql_assets_id"), "dm_sql_assets", ["id"], unique=False)
        op.create_index(
            op.f("ix_dm_sql_assets_owner_user_id"),
            "dm_sql_assets",
            ["owner_user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_dm_sql_assets_system_short"),
            "dm_sql_assets",
            ["system_short"],
            unique=False,
        )

    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_sql_asset_versions" not in existing_tables:
        op.create_table(
            "dm_sql_asset_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sql_asset_id", sa.Integer(), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("connection_config", sa.JSON(), nullable=False),
            sa.Column("whitelist", sa.JSON(), nullable=False),
            sa.Column("blacklist", sa.JSON(), nullable=False),
            sa.Column("mutation_enabled", sa.Boolean(), nullable=False),
            sa.Column("review_comment", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["sql_asset_id"], ["dm_sql_assets.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_dm_sql_asset_versions_id"),
            "dm_sql_asset_versions",
            ["id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_dm_sql_asset_versions_sql_asset_id"),
            "dm_sql_asset_versions",
            ["sql_asset_id"],
            unique=False,
        )

    with op.batch_alter_table("dm_sql_assets", schema=None) as batch_op:
        try:
            batch_op.create_foreign_key(
                "fk_dm_sql_assets_current_active_version_id",
                "dm_sql_asset_versions",
                ["current_active_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
        except Exception:
            pass


def downgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "dm_sql_assets" in existing_tables:
        with op.batch_alter_table("dm_sql_assets", schema=None) as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_dm_sql_assets_current_active_version_id", type_="foreignkey"
                )
            except Exception:
                pass

    if "dm_sql_asset_versions" in existing_tables:
        op.drop_index(
            op.f("ix_dm_sql_asset_versions_sql_asset_id"),
            table_name="dm_sql_asset_versions",
        )
        op.drop_index(
            op.f("ix_dm_sql_asset_versions_id"),
            table_name="dm_sql_asset_versions",
        )
        op.drop_table("dm_sql_asset_versions")

    if "dm_sql_assets" in existing_tables:
        op.drop_index(
            op.f("ix_dm_sql_assets_system_short"), table_name="dm_sql_assets"
        )
        op.drop_index(
            op.f("ix_dm_sql_assets_owner_user_id"), table_name="dm_sql_assets"
        )
        op.drop_index(op.f("ix_dm_sql_assets_id"), table_name="dm_sql_assets")
        op.drop_table("dm_sql_assets")

    if "dm_http_assets" in existing_tables:
        op.drop_index(
            op.f("ix_dm_http_assets_system_short"), table_name="dm_http_assets"
        )
        op.drop_index(
            op.f("ix_dm_http_assets_owner_user_id"), table_name="dm_http_assets"
        )
        op.drop_index(op.f("ix_dm_http_assets_id"), table_name="dm_http_assets")
        op.drop_table("dm_http_assets")
