from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class DMHTTPAsset(Base):  # type: ignore
    """HTTP 资产对象。

    这个模型保存探索态和模板收敛时会引用的 HTTP 资产定义。
    当前 V1 先采用单表模式，不引入版本层，重点先把可管理的最小真相源补齐。
    """

    __tablename__ = "dm_http_assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_short = Column(String(64), nullable=False, index=True)
    base_url = Column(String(1024), nullable=False)
    method = Column(String(16), nullable=False)
    path_template = Column(String(1024), nullable=False)
    query_template = Column(JSON, nullable=True)
    headers_template = Column(JSON, nullable=True)
    body_template = Column(JSON, nullable=True)
    request_schema = Column(JSON, nullable=True)
    auth_type = Column(String(64), nullable=True)
    # 这里只存密文或占位结构，不在 API 响应中回传敏感配置。
    auth_config_ciphertext = Column(Text, nullable=True)
    response_extraction_rules = Column(JSON, nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    max_response_bytes = Column(Integer, nullable=False, default=1048576)
    enabled = Column(Boolean, nullable=False, default=True)
    owner_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", foreign_keys=[owner_user_id])

    def __repr__(self) -> str:
        return f"<DMHTTPAsset(id={self.id}, name='{self.name}', method='{self.method}')>"


class DMSQLAsset(Base):  # type: ignore
    """SQL 资产逻辑对象。

    它回答“这是什么 SQL 资产”，但不直接承载某一版连接与治理配置。
    具体可审核、可生效的配置放在 `DMSQLAssetVersion`。
    """

    __tablename__ = "dm_sql_assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_short = Column(String(64), nullable=False, index=True)
    owner_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_active_version_id = Column(
        Integer,
        ForeignKey("dm_sql_asset_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", foreign_keys=[owner_user_id])
    versions = relationship(
        "DMSQLAssetVersion",
        foreign_keys="DMSQLAssetVersion.sql_asset_id",
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by="DMSQLAssetVersion.created_at",
    )
    current_active_version = relationship(
        "DMSQLAssetVersion",
        foreign_keys=[current_active_version_id],
        post_update=True,
    )

    def __repr__(self) -> str:
        return f"<DMSQLAsset(id={self.id}, name='{self.name}', system_short='{self.system_short}')>"


class DMSQLAssetVersion(Base):  # type: ignore
    """SQL 资产版本对象。

    这里承载真正参与治理审核和执行锁定的配置内容：
    - 连接配置
    - 白名单 / 黑名单
    - mutation 开关
    - 审核状态与审核人
    """

    __tablename__ = "dm_sql_asset_versions"

    id = Column(Integer, primary_key=True, index=True)
    sql_asset_id = Column(
        Integer,
        ForeignKey("dm_sql_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    connection_config = Column(JSON, nullable=False, default=dict)
    whitelist = Column(JSON, nullable=False, default=list)
    blacklist = Column(JSON, nullable=False, default=list)
    mutation_enabled = Column(Boolean, nullable=False, default=False)
    review_comment = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    asset = relationship(
        "DMSQLAsset",
        foreign_keys=[sql_asset_id],
        back_populates="versions",
    )
    creator = relationship("User", foreign_keys=[created_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return (
            f"<DMSQLAssetVersion(id={self.id}, sql_asset_id={self.sql_asset_id}, "
            f"version_no={self.version_no}, status='{self.status}')>"
        )
