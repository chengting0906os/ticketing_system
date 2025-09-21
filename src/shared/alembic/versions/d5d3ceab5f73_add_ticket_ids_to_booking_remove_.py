"""add_ticket_ids_to_booking_remove_booking_id_from_ticket

Revision ID: d5d3ceab5f73
Revises: 0c7da820d4e5
Create Date: 2025-09-21 21:15:22.186468

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5d3ceab5f73'
down_revision: Union[str, Sequence[str], None] = '0c7da820d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add ticket_ids array to booking table
    op.add_column(
        'booking',
        sa.Column('ticket_ids', sa.ARRAY(sa.Integer()), nullable=False, server_default='{}'),
    )
    op.add_column('booking', sa.Column('seat_selection_mode', sa.String(length=20), nullable=True))

    # Rename price to total_price in booking table for clarity
    op.alter_column('booking', 'price', new_column_name='total_price')

    # Remove booking_id foreign key constraint and column from ticket table
    op.drop_constraint('ticket_booking_id_fkey', 'ticket', type_='foreignkey')
    op.drop_column('ticket', 'booking_id')


def downgrade() -> None:
    """Downgrade schema."""
    # Add booking_id back to ticket table
    op.add_column('ticket', sa.Column('booking_id', sa.INTEGER(), nullable=True))
    op.create_foreign_key('ticket_booking_id_fkey', 'ticket', 'booking', ['booking_id'], ['id'])

    # Revert booking table changes
    op.alter_column('booking', 'total_price', new_column_name='price')
    op.drop_column('booking', 'seat_selection_mode')
    op.drop_column('booking', 'ticket_ids')
