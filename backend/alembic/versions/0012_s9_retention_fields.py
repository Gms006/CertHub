"""add retention fields to cert_install_jobs

Revision ID: 0012_s9_retention_fields
Revises: 0011_merge_0010_heads
Create Date: 2025-03-03 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0012_s9_retention_fields"
down_revision = "0011_merge_0010_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cert_install_jobs",
        sa.Column("cleanup_mode", sa.String(), nullable=False, server_default=sa.text("'DEFAULT'")),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("keep_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("keep_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("keep_set_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("keep_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cert_install_jobs_keep_set_by_user_id_users",
        "cert_install_jobs",
        "users",
        ["keep_set_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_cert_install_jobs_cleanup_mode_keep_until",
        "cert_install_jobs",
        ["cleanup_mode", "keep_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cert_install_jobs_cleanup_mode_keep_until", table_name="cert_install_jobs")
    op.drop_constraint(
        "fk_cert_install_jobs_keep_set_by_user_id_users",
        "cert_install_jobs",
        type_="foreignkey",
    )
    op.drop_column("cert_install_jobs", "keep_set_at")
    op.drop_column("cert_install_jobs", "keep_set_by_user_id")
    op.drop_column("cert_install_jobs", "keep_reason")
    op.drop_column("cert_install_jobs", "keep_until")
    op.drop_column("cert_install_jobs", "cleanup_mode")
