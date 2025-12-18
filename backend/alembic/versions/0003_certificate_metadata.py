"""certificate metadata fields

Revision ID: 0003_certificate_metadata
Revises: 0002_rbac_auto_approve_jobs
Create Date: 2025-03-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_certificate_metadata"
down_revision = "0002_rbac_auto_approve_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("certificates", sa.Column("subject", sa.String(), nullable=True))
    op.add_column("certificates", sa.Column("issuer", sa.String(), nullable=True))
    op.add_column("certificates", sa.Column("serial_number", sa.String(), nullable=True))
    op.add_column(
        "certificates",
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("certificates", sa.Column("sha1_fingerprint", sa.String(), nullable=True))
    op.add_column("certificates", sa.Column("parse_error", sa.String(), nullable=True))
    op.add_column("certificates", sa.Column("source_path", sa.String(), nullable=True))

    op.create_index(
        "ix_certificates_org_id_sha1",
        "certificates",
        ["org_id", "sha1_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_certificates_org_id_serial",
        "certificates",
        ["org_id", "serial_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_certificates_org_id_serial", table_name="certificates")
    op.drop_index("ix_certificates_org_id_sha1", table_name="certificates")
    op.drop_column("certificates", "source_path")
    op.drop_column("certificates", "parse_error")
    op.drop_column("certificates", "sha1_fingerprint")
    op.drop_column("certificates", "not_after")
    op.drop_column("certificates", "not_before")
    op.drop_column("certificates", "serial_number")
    op.drop_column("certificates", "issuer")
    op.drop_column("certificates", "subject")
