"""为 users 表补充旧系统 SSO 识别字段。

Revision ID: 20260324_add_legacy_sso_fields_to_users
Revises: 20260324_add_datamakepool_runtime_and_templates
Create Date: 2026-03-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "20260324_add_legacy_sso_fields_to_users"
down_revision: Union[str, None] = "20260324_add_datamakepool_runtime_and_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()
    if "users" not in existing_tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}

    if "external_user_id" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("external_user_id", sa.String(length=128), nullable=True),
        )

    if "email" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("email", sa.String(length=255), nullable=True),
        )

    if "oa_account" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("oa_account", sa.String(length=128), nullable=True),
        )

    if "ix_users_external_user_id" not in existing_indexes:
        op.create_index(
            "ix_users_external_user_id",
            "users",
            ["external_user_id"],
            unique=True,
        )


def downgrade() -> None:
    from alembic import context

    bind = context.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()
    if "users" not in existing_tables:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("users")}

    if "ix_users_external_user_id" in existing_indexes:
        op.drop_index("ix_users_external_user_id", table_name="users")

    if "oa_account" in existing_columns:
        op.drop_column("users", "oa_account")

    if "email" in existing_columns:
        op.drop_column("users", "email")

    if "external_user_id" in existing_columns:
        op.drop_column("users", "external_user_id")
