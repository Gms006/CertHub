"""add auth tokens and user sessions

Revision ID: 0007_auth_tokens_sessions
Revises: 0006_remove_user_emp_perm
Create Date: 2025-02-10 00:00:01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007_auth_tokens_sessions"
down_revision = "0006_remove_user_emp_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(), nullable=True))
    op.add_column("users", sa.Column("password_set_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "auth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_tokens_token_hash_purpose_expires_at",
        "auth_tokens",
        ["token_hash", "purpose", "expires_at"],
        unique=False,
    )

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_user_sessions_refresh_token_hash_user_id",
        "user_sessions",
        ["refresh_token_hash", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_refresh_token_hash_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_auth_tokens_token_hash_purpose_expires_at", table_name="auth_tokens")
    op.drop_table("auth_tokens")

    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "password_set_at")
    op.drop_column("users", "password_hash")
