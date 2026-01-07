"""add retention policy flags to devices

Revision ID: 0013_device_retention_flags
Revises: 0012_s9_retention_fields
Create Date: 2025-03-03 00:00:01
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0013_device_retention_flags"
down_revision = "0012_s9_retention_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("allow_keep_until", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "devices",
        sa.Column("allow_exempt", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("devices", "allow_exempt")
    op.drop_column("devices", "allow_keep_until")
