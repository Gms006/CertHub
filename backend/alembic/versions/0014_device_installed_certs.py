"""add device installed certs snapshot table

Revision ID: 0014_device_installed_certs
Revises: 0013_device_retention_flags
Create Date: 2025-03-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0014_device_installed_certs"
down_revision = "0013_device_retention_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_installed_certs",
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thumbprint", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("issuer", sa.String(), nullable=True),
        sa.Column("serial", sa.String(), nullable=True),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_via_agent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cleanup_mode", sa.String(), nullable=True),
        sa.Column("keep_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("keep_reason", sa.Text(), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["cert_install_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("org_id", "device_id", "thumbprint"),
    )
    op.create_index(
        "ix_device_installed_certs_device_id",
        "device_installed_certs",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        "ix_device_installed_certs_last_seen_at",
        "device_installed_certs",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_device_installed_certs_removed_at",
        "device_installed_certs",
        ["removed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_device_installed_certs_removed_at", table_name="device_installed_certs")
    op.drop_index("ix_device_installed_certs_last_seen_at", table_name="device_installed_certs")
    op.drop_index("ix_device_installed_certs_device_id", table_name="device_installed_certs")
    op.drop_table("device_installed_certs")
