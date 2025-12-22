"""add assigned user to devices

Revision ID: 0008_device_assigned_user
Revises: 0007_auth_tokens_sessions
Create Date: 2025-02-10 00:00:02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_device_assigned_user"
down_revision = "0007_auth_tokens_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_devices_assigned_user_id_users",
        "devices",
        "users",
        ["assigned_user_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )
    op.create_index("ix_devices_assigned_user_id", "devices", ["assigned_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_assigned_user_id", table_name="devices")
    op.drop_constraint("fk_devices_assigned_user_id_users", "devices", type_="foreignkey")
    op.drop_column("devices", "assigned_user_id")
