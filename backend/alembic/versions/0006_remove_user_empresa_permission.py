"""remove user empresa permission table

Revision ID: 0006_remove_user_empresa_permission
Revises: 0005_user_updated_at
Create Date: 2025-02-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006_remove_user_empresa_permission"
down_revision = "0005_user_updated_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_user_empresa_permission_org_id", table_name="user_empresa_permission")
    op.drop_table("user_empresa_permission")


def downgrade() -> None:
    op.create_table(
        "user_empresa_permission",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "user_id", "empresa_id", "role", name="uq_user_empresa_role"),
    )
    op.create_index("ix_user_empresa_permission_org_id", "user_empresa_permission", ["org_id"], unique=False)
