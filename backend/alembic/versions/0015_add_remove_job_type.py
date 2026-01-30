"""add remove job type support

Revision ID: 0015_add_remove_job_type
Revises: 0014_device_installed_certs
Create Date: 2025-03-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0015_add_remove_job_type"
down_revision = "0014_device_installed_certs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cert_install_jobs",
        sa.Column("job_type", sa.String(), server_default=sa.text("'INSTALL'"), nullable=False),
    )
    op.add_column(
        "cert_install_jobs",
        sa.Column("target_thumbprint", sa.String(), nullable=True),
    )
    op.alter_column(
        "cert_install_jobs",
        "cert_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    remove_jobs = bind.execute(
        sa.text(
            "SELECT COUNT(1) FROM cert_install_jobs WHERE job_type = 'REMOVE_CERT' OR cert_id IS NULL"
        )
    ).scalar()
    if remove_jobs and int(remove_jobs) > 0:
        raise RuntimeError(
            "Downgrade blocked: cert_install_jobs contains REMOVE_CERT jobs or NULL cert_id entries."
        )

    op.alter_column(
        "cert_install_jobs",
        "cert_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("cert_install_jobs", "target_thumbprint")
    op.drop_column("cert_install_jobs", "job_type")
