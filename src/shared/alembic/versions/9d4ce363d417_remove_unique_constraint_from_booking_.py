"""remove_unique_constraint_from_booking_ticket_ids

Revision ID: 9d4ce363d417
Revises: abc123456790
Create Date: 2025-09-22 14:08:46.097709

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9d4ce363d417'
down_revision: Union[str, Sequence[str], None] = 'abc123456790'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unique constraint from booking.ticket_ids array column."""
    op.drop_constraint('uq_booking_ticket_ids', 'booking', type_='unique')


def downgrade() -> None:
    """Re-add unique constraint to booking.ticket_ids array column."""
    # Clean up potential duplicate data before re-adding constraint
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

    op.create_unique_constraint('uq_booking_ticket_ids', 'booking', ['ticket_ids'])
