"""add updated_at to users

Revision ID: 0005_user_updated_at
Revises: 0004_certificate_parse_status
Create Date: 2025-03-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_user_updated_at"
down_revision = "0004_certificate_parse_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "updated_at")
