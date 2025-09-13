"""add_reservation_fields_to_ticket

Revision ID: b801189f4441
Revises: a0bf82d09f3b
Create Date: 2025-09-13 19:38:38.850224

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b801189f4441'
down_revision: Union[str, Sequence[str], None] = 'a0bf82d09f3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new reservation field to ticket table
    op.add_column('ticket', sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove reservation field from ticket table
    op.drop_column('ticket', 'reserved_at')
