"""create s1 tables

Revision ID: 0001_create_s1_tables
Revises: 
Create Date: 2024-11-17 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_create_s1_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("ad_username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("nome", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "ad_username", name="uq_users_org_id_ad_username"),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"], unique=False)
    op.create_index("ix_users_ad_username", "users", ["ad_username"], unique=False)

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("hostname", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("os_version", sa.String(), nullable=True),
        sa.Column("agent_version", sa.String(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "hostname", name="uq_devices_org_id_hostname"),
    )
    op.create_index("ix_devices_org_id", "devices", ["org_id"], unique=False)
    op.create_index("ix_devices_hostname", "devices", ["hostname"], unique=False)

    op.create_table(
        "user_device",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "device_id", name="pk_user_device"),
    )

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

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"], unique=False)
    op.create_index("ix_audit_log_org_id", "audit_log", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_org_id", table_name="audit_log")
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_user_empresa_permission_org_id", table_name="user_empresa_permission")
    op.drop_table("user_empresa_permission")

    op.drop_table("user_device")

    op.drop_index("ix_devices_hostname", table_name="devices")
    op.drop_index("ix_devices_org_id", table_name="devices")
    op.drop_table("devices")

    op.drop_index("ix_users_ad_username", table_name="users")
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_table("users")
