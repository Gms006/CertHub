"""add agent mvp fields

Revision ID: 0009_agent_mvp_fields
Revises: 0008_device_assigned_user
Create Date: 2025-02-10 00:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0009_agent_mvp_fields"
down_revision = "0008_device_assigned_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("device_token_hash", sa.String(), nullable=True))
    op.add_column("devices", sa.Column("token_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "cert_install_jobs",
        sa.Column("claimed_by_device_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("cert_install_jobs", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cert_install_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cert_install_jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cert_install_jobs", sa.Column("error_code", sa.String(), nullable=True))
    op.add_column("cert_install_jobs", sa.Column("error_message", sa.String(), nullable=True))
    op.add_column("cert_install_jobs", sa.Column("thumbprint", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_cert_install_jobs_claimed_by_device_id_devices",
        "cert_install_jobs",
        "devices",
        ["claimed_by_device_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_cert_install_jobs_claimed_by_device_id_devices", "cert_install_jobs", type_="foreignkey"
    )
    op.drop_column("cert_install_jobs", "thumbprint")
    op.drop_column("cert_install_jobs", "error_message")
    op.drop_column("cert_install_jobs", "error_code")
    op.drop_column("cert_install_jobs", "finished_at")
    op.drop_column("cert_install_jobs", "started_at")
    op.drop_column("cert_install_jobs", "claimed_at")
    op.drop_column("cert_install_jobs", "claimed_by_device_id")

    op.drop_column("devices", "last_heartbeat_at")
    op.drop_column("devices", "token_created_at")
    op.drop_column("devices", "device_token_hash")
