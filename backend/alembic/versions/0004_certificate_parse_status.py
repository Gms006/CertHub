"""certificate parse status fields

Revision ID: 0004_certificate_parse_status
Revises: 0003_certificate_metadata
Create Date: 2025-03-05 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_certificate_parse_status"
down_revision = "0003_certificate_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "certificates", sa.Column("parse_ok", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "certificates",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("certificates", "last_error_at")
    op.drop_column("certificates", "last_ingested_at")
    op.drop_column("certificates", "parse_ok")
