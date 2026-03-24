from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class User(Base):  # type: ignore
    """用户模型。

    这个模型同时承载两类身份来源：
    1. 本项目原生用户名密码账号
    2. 从旧系统跳转进来的 SSO 账号

    当前这次改造里，SSO 用户的长期归属键不是 username，
    而是 external_user_id。这样即使旧系统展示名变化，
    也不会把人识别错。
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # username 仍然保留给前端展示和系统内兼容逻辑使用，
    # 但对 SSO 用户来说，它不再是跨系统身份主键。
    username = Column(String(50), unique=True, index=True, nullable=False)
    # password_hash 由于历史原因仍然是必填字段。
    # SSO 自动创建用户时会写入一个随机不可复用的密码哈希，
    # 仅用于满足数据库约束，不代表允许本地密码登录。
    password_hash = Column(String(255), nullable=False)
    # external_user_id 是旧系统稳定传入的唯一身份标识。
    # 本项目后续所有 SSO 识别、自动建人、重复登录归属，
    # 都应该优先依赖它，而不是 username/email。
    external_user_id = Column(String(128), unique=True, index=True, nullable=True)
    # 以下字段主要用于同步旧系统的人信息，便于后续展示和排查。
    email = Column(String(255), nullable=True)
    oa_account = Column(String(128), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)  # Admin role flag
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    refresh_token = Column(String(255), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tasks = relationship("Task", back_populates="user")
    agents = relationship("Agent", back_populates="user")
    mcp_servers = relationship(
        "MCPServer",
        secondary="user_mcpservers",
        primaryjoin="User.id==UserMCPServer.user_id",
        secondaryjoin="MCPServer.id==UserMCPServer.mcpserver_id",
        viewonly=True,
    )
    user_mcpservers = relationship(
        "UserMCPServer", back_populates="user", cascade="all, delete-orphan"
    )
    text2sql_databases = relationship(
        "Text2SQLDatabase", back_populates="user", cascade="all, delete-orphan"
    )
    user_models = relationship(
        "UserModel", back_populates="user", cascade="all, delete-orphan"
    )
    uploaded_files = relationship(
        "UploadedFile", back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages = relationship(
        "TaskChatMessage", back_populates="user", cascade="all, delete-orphan"
    )
    user_default_models = relationship(
        "UserDefaultModel", back_populates="user", cascade="all, delete-orphan"
    )
    oauth_accounts = relationship(
        "UserOAuth", back_populates="user", cascade="all, delete-orphan"
    )
    admin_system_scopes = relationship(
        "AdminSystemScope", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, username='{self.username}', "
            f"external_user_id='{self.external_user_id}', is_admin={self.is_admin})>"
        )


class UserModel(Base):  # type: ignore
    """User-Model relationship table for model ownership and sharing"""

    __tablename__ = "user_models"
    __table_args__ = (UniqueConstraint("user_id", "model_id", name="uq_user_model"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model_id = Column(
        Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    is_owner = Column(
        Boolean, default=False, nullable=False
    )  # True if user created the model
    can_edit = Column(
        Boolean, default=False, nullable=False
    )  # True if user can edit the model
    can_delete = Column(
        Boolean, default=False, nullable=False
    )  # True if user can delete the model
    is_shared = Column(
        Boolean, default=False, nullable=False
    )  # True if model is shared by admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="user_models")
    model = relationship("Model", back_populates="user_models")

    def __repr__(self) -> str:
        return f"<UserModel(user_id={self.user_id}, model_id={self.model_id}, is_owner={self.is_owner})>"


class UserDefaultModel(Base):  # type: ignore
    """User default model configurations"""

    __tablename__ = "user_default_models"
    __table_args__ = (
        UniqueConstraint("user_id", "config_type", name="uq_user_default_model"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model_id = Column(
        Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False
    )
    config_type = Column(
        String(50), nullable=False
    )  # 'general', 'small_fast', 'visual', 'compact', 'embedding'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="user_default_models")
    model = relationship("Model", back_populates="user_default_models")

    def __repr__(self) -> str:
        return f"<UserDefaultModel(user_id={self.user_id}, config_type='{self.config_type}', model_id={self.model_id})>"
