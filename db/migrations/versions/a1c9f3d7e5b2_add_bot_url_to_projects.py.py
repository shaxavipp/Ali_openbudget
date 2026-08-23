"""add bot_url to projects

Revision ID: a1c9f3d7e5b2
Revises: 5a921d9062ea
Create Date: 2026-08-23 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c9f3d7e5b2'
down_revision: Union[str, Sequence[str], None] = '5a921d9062ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('bot_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'bot_url')
