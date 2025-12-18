import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JOB_STATUS_REQUESTED = "REQUESTED"
JOB_STATUS_PENDING = "PENDING"
JOB_STATUS_IN_PROGRESS = "IN_PROGRESS"
JOB_STATUS_DONE = "DONE"
JOB_STATUS_FAILED = "FAILED"
JOB_STATUS_EXPIRED = "EXPIRED"
JOB_STATUS_CANCELED = "CANCELED"


class CertInstallJob(Base):
    __tablename__ = "cert_install_jobs"
    __table_args__ = (
        Index("ix_cert_install_jobs_org_status_created_at", "org_id", "status", "created_at"),
        Index("ix_cert_install_jobs_approved_by_user_id", "approved_by_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("certificates.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=JOB_STATUS_REQUESTED)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
