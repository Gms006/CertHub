import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("org_id", "ad_username", name="uq_users_org_id_ad_username"),
        Index("ix_users_org_id", "org_id"),
        Index("ix_users_ad_username", "ad_username"),
        Index("ix_users_org_id_role_global", "org_id", "role_global"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ad_username: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    nome: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    role_global: Mapped[str] = mapped_column(String, nullable=False, server_default="VIEW")
    auto_approve_install_jobs: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
