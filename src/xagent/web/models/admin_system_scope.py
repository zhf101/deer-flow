from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class AdminSystemScope(Base):  # type: ignore
    """Maps a domain admin to one or more systemShort scopes."""

    __tablename__ = "admin_system_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "system_short", name="uq_admin_system_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    system_short = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="admin_system_scopes")

    def __repr__(self) -> str:
        return (
            f"<AdminSystemScope(user_id={self.user_id}, "
            f"system_short='{self.system_short}')>"
        )
