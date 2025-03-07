"""Add user_id to StatementPeriod

Revision ID: 59a7819f3116
Revises: 92b205d2adea
Create Date: 2025-03-06 22:40:42.414745

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59a7819f3116'
down_revision: Union[str, None] = '92b205d2adea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
