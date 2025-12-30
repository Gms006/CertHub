"""add payload token fields to cert_install_jobs

Revision ID: 0009_job_payload_tokens
Revises: 0008_device_assigned_user
Create Date: 2025-02-10 00:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_job_payload_tokens"
down_revision = "0008_device_assigned_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cert_install_jobs", sa.Column("payload_token_hash", sa.Text(), nullable=True))
    op.add_column(
        "cert_install_jobs",
        sa.Column("payload_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("payload_token_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("payload_token_device_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cert_install_jobs_payload_token_device_id_devices",
        "cert_install_jobs",
        "devices",
        ["payload_token_device_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_cert_install_jobs_payload_token_device_id_devices",
        "cert_install_jobs",
        type_="foreignkey",
    )
    op.drop_column("cert_install_jobs", "payload_token_device_id")
    op.drop_column("cert_install_jobs", "payload_token_used_at")
    op.drop_column("cert_install_jobs", "payload_token_expires_at")
    op.drop_column("cert_install_jobs", "payload_token_hash")
