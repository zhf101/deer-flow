"""SQLAlchemy rows for GDP data-factory configuration."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class DataFactorySceneRow(Base):
    __tablename__ = "df_scene"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scene_name: Mapped[str] = mapped_column(String(256), nullable=False)
    scene_remark: Mapped[str | None] = mapped_column(Text)
    scene_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_version_no: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(128))
    updated_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("idx_df_scene_type", "scene_type"),
        Index("idx_df_scene_status", "status"),
    )


class DataFactorySceneVersionRow(Base):
    __tablename__ = "df_scene_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_status: Mapped[str] = mapped_column(String(32), nullable=False)
    environment_field: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    steps_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    batch_config_json: Mapped[str | None] = mapped_column(Text)
    validation_result_json: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    published_by: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("scene_id", "version_no", name="uq_df_scene_version"),
        Index("idx_df_scene_version_scene_code", "scene_code"),
        Index("idx_df_scene_version_status", "version_status"),
    )


class DataFactoryEnvironmentRow(Base):
    __tablename__ = "df_environment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    env_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class DataFactoryServiceEndpointRow(Base):
    __tablename__ = "df_service_endpoint"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False)
    service_code: Mapped[str] = mapped_column(String(128), nullable=False)
    service_name: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("env_code", "service_code", name="uq_df_service_endpoint"),)


class DataFactoryDatasourceRow(Base):
    __tablename__ = "df_datasource"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False)
    datasource_code: Mapped[str] = mapped_column(String(128), nullable=False)
    datasource_name: Mapped[str] = mapped_column(String(256), nullable=False)
    db_type: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(256), nullable=False)
    username: Mapped[str | None] = mapped_column(String(512))
    password: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("env_code", "datasource_code", name="uq_df_datasource"),)


class DataFactorySqlTemplateRow(Base):
    __tablename__ = "df_sql_template"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    template_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    datasource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    safety_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    updated_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class DataFactoryConfigAuditRow(Base):
    __tablename__ = "df_config_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str | None] = mapped_column(String(128))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
