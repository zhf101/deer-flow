"""GDP 造数工厂 SQLAlchemy ORM 行模型。定义所有数据库表结构。

包含以下核心表：
- df_scene          场景主表，记录场景元信息与当前状态
- df_scene_version  场景版本表，每次编辑产生一条版本快照
- df_environment    环境配置表（DEV / SIT / PROD 等）
- df_service_endpoint 服务端点表，记录各环境下 HTTP 服务的 base_url
- df_datasource     数据源表，记录各环境下数据库连接信息
- df_sql_template   SQL 模板表，存放可复用的参数化 SQL 语句
- df_config_audit   配置审计表，记录所有配置变更的操作日志
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _now() -> datetime:
    """返回当前 UTC 时间，用作行记录的默认时间戳。"""
    return datetime.now(UTC)


# ========================= 场景主表 =========================
# 存储造数场景的顶层元信息，scene_code 为业务唯一键
class DataFactorySceneRow(Base):
    """场景主表行模型。

    一条记录对应一个造数场景，维护场景编码、名称、类型、状态及当前发布版本号。
    状态流转：DRAFT -> PUBLISHED -> DISABLED。
    """
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
        # 按场景类型和状态建立索引，加速列表过滤查询
        Index("idx_df_scene_type", "scene_type"),
        Index("idx_df_scene_status", "status"),
    )


# ========================= 场景版本表 =========================
# 每次场景编辑都会生成一条版本记录，保留完整的配置快照用于回溯和审计
class DataFactorySceneVersionRow(Base):
    """场景版本表行模型。

    以 scene_id + version_no 联合唯一，存储某一版本的完整配置：
    输入参数定义、步骤编排、结果映射、批量配置以及校验结果。
    """
    __tablename__ = "df_scene_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    version_status: Mapped[str] = mapped_column(String(32), nullable=False)
    environment_field: Mapped[str] = mapped_column(String(64), nullable=False)
    # 以下 JSON 字段存储序列化后的完整配置快照
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
        # 同一场景下版本号唯一
        UniqueConstraint("scene_id", "version_no", name="uq_df_scene_version"),
        Index("idx_df_scene_version_scene_code", "scene_code"),
        Index("idx_df_scene_version_status", "version_status"),
    )


# ========================= 环境配置表 =========================
# 定义造数支持的目标环境，如 DEV、SIT、UAT、PROD
class DataFactoryEnvironmentRow(Base):
    """环境配置表行模型。

    env_code 为业务唯一键，标识一个目标运行环境。
    """
    __tablename__ = "df_environment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    env_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ========================= 服务端点表 =========================
# 记录各环境下 HTTP 服务的 base_url，供场景 HTTP 步骤解析目标地址
class DataFactoryServiceEndpointRow(Base):
    """服务端点表行模型。

    以 env_code + service_code 联合唯一，确保同一环境下同一服务只有一个端点地址。
    """
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


# ========================= 数据源表 =========================
# 记录各环境下的数据库连接信息，供场景 SQL 步骤选择目标库
class DataFactoryDatasourceRow(Base):
    """数据源表行模型。

    以 env_code + datasource_code 联合唯一，包含主机、端口、库名、账密等连接参数。
    """
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


# ========================= SQL 模板表 =========================
# 存放可复用的参数化 SQL 语句模板，供 SQL 步骤引用
class DataFactorySqlTemplateRow(Base):
    """SQL 模板表行模型。

    template_code 为业务唯一键，存储 SQL 文本、参数定义、安全策略等。
    模板可被多个场景的 SQL 步骤共享引用。
    """
    __tablename__ = "df_sql_template"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    template_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    datasource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON 格式的参数定义列表和安全性配置
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    safety_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    updated_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ========================= 配置审计表 =========================
# 记录所有配置变更的操作日志，用于合规审计和问题追溯
class DataFactoryConfigAuditRow(Base):
    """配置审计表行模型。

    记录每次配置变更的操作类型（CREATE / UPDATE / PUBLISH / DISABLE / DELETE）、
    操作人、变更前后的 JSON 快照，形成完整的变更轨迹。
    """
    __tablename__ = "df_config_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str | None] = mapped_column(String(128))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
