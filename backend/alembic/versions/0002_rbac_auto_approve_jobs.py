"""rbac auto approve jobs

Revision ID: 0002_rbac_auto_approve_jobs
Revises: 0001_create_s1_tables
Create Date: 2025-02-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_rbac_auto_approve_jobs"
down_revision = "0001_create_s1_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role_global", sa.String(), nullable=False, server_default="VIEW"),
    )
    op.add_column(
        "users",
        sa.Column(
            "auto_approve_install_jobs", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_index("ix_users_org_id_role_global", "users", ["org_id", "role_global"], unique=False)

    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_certificates_org_id_name"),
    )
    op.create_index("ix_certificates_org_id", "certificates", ["org_id"], unique=False)

    op.create_table(
        "cert_install_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("cert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("certificates.id", ondelete="CASCADE")),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="REQUESTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index(
        "ix_cert_install_jobs_org_status_created_at",
        "cert_install_jobs",
        ["org_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_cert_install_jobs_approved_by_user_id",
        "cert_install_jobs",
        ["approved_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cert_install_jobs_approved_by_user_id", table_name="cert_install_jobs")
    op.drop_index("ix_cert_install_jobs_org_status_created_at", table_name="cert_install_jobs")
    op.drop_table("cert_install_jobs")

    op.drop_index("ix_certificates_org_id", table_name="certificates")
    op.drop_table("certificates")

    op.drop_index("ix_users_org_id_role_global", table_name="users")
    op.drop_column("users", "auto_approve_install_jobs")
    op.drop_column("users", "role_global")
