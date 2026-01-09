import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceInstalledCert(Base):
    __tablename__ = "device_installed_certs"
    __table_args__ = (
        Index("ix_device_installed_certs_device_id", "device_id"),
        Index("ix_device_installed_certs_last_seen_at", "last_seen_at"),
        Index("ix_device_installed_certs_removed_at", "removed_at"),
    )

    org_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    thumbprint: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String, nullable=True)
    serial: Mapped[str | None] = mapped_column(String, nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    installed_via_agent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cleanup_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    keep_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keep_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cert_install_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
