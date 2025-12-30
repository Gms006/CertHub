"""merge 0009 heads

Revision ID: 0010_merge_0009_heads
Revises: 0009_agent_mvp_fields, 0009_job_payload_tokens
Create Date: 2025-12-30 10:51:41.702236
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_merge_0009_heads'
down_revision = ('0009_agent_mvp_fields', '0009_job_payload_tokens')
branch_labels = None
depends_on = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
