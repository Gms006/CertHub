"""merge 0010 heads.

Revision ID: 0011_merge_0010_heads
Revises: 0010_device_auto_approve, 0010_merge_0009_heads
Create Date: 2025-02-14 00:30:00.000000
"""

# pylint: disable=unused-import

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_merge_0010_heads"
down_revision = ("0010_device_auto_approve", "0010_merge_0009_heads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
