"""add_unique_constraint_to_booking_ticket_ids

Revision ID: 070c0eadd71e
Revises: d5d3ceab5f73
Create Date: 2025-09-22 01:34:11.684558

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '070c0eadd71e'
down_revision: Union[str, Sequence[str], None] = 'd5d3ceab5f73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to booking.ticket_ids array column."""

    # First, clean up duplicate data by keeping only the latest booking for each ticket_ids set
    op.execute("""
        DELETE FROM booking
        WHERE id NOT IN (
            SELECT DISTINCT ON (ticket_ids) id
            FROM booking
            ORDER BY ticket_ids, created_at DESC
        )
        AND ticket_ids IS NOT NULL
        AND array_length(ticket_ids, 1) > 0
    """)

    # Then create a unique constraint on the ticket_ids array column
    # This ensures that no two bookings can have the same set of tickets
    op.create_unique_constraint('uq_booking_ticket_ids', 'booking', ['ticket_ids'])


def downgrade() -> None:
    """Remove unique constraint from booking.ticket_ids array column."""
    op.drop_constraint('uq_booking_ticket_ids', 'booking', type_='unique')
