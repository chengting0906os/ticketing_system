"""remove_model_defaults

Revision ID: cc204770957e
Revises: 6a7d1902f1b9
Create Date: 2025-09-13 16:12:26.315494

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cc204770957e'
down_revision: Union[str, Sequence[str], None] = '6a7d1902f1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove only inappropriate default values from event table
    op.alter_column('event', 'venue_name', server_default=None)
    op.alter_column('event', 'seating_config', server_default=None)


def downgrade() -> None:
    # Restore inappropriate default values to event table
    op.alter_column('event', 'venue_name', server_default='Default Venue')
    op.alter_column(
        'event',
        'seating_config',
        server_default='{"sections": 10, "rows_per_section": 25, "seats_per_row": 20}',
    )
