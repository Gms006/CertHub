"""add device auto_approve flag.

Revision ID: 0010_device_auto_approve
Revises: 0009_job_payload_tokens
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_device_auto_approve"
down_revision = ("0009_job_payload_tokens", "0009_agent_mvp_fields")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "auto_approve",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "auto_approve")
