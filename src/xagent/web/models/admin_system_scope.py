from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class AdminSystemScope(Base):  # type: ignore
    """普通管理员与 systemShort 的绑定关系。

    这个模型不是业务对象本身，而是权限路由基础表。
    后续 datamakepool 的对象级过滤与审核路由，都会依赖它来判断
    当前普通管理员能覆盖哪些 systemShort。
    """

    __tablename__ = "admin_system_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "system_short", name="uq_admin_system_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # system_short 是审核路由与对象归属范围，不是普通用户使用隔离字段。
    system_short = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="admin_system_scopes")

    def __repr__(self) -> str:
        return (
            f"<AdminSystemScope(user_id={self.user_id}, "
            f"system_short='{self.system_short}')>"
        )
