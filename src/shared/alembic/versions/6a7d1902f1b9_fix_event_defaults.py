"""fix_event_defaults

Revision ID: 6a7d1902f1b9
Revises: 7df8a81f1af9
Create Date: 2025-09-13 15:58:38.699384

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6a7d1902f1b9'
down_revision: Union[str, Sequence[str], None] = '7df8a81f1af9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix event table default values."""
    # Set default values for existing rows
    op.execute(
        "UPDATE event SET venue_name = 'Default Venue' WHERE venue_name IS NULL OR venue_name = ''"
    )
    op.execute(
        'UPDATE event SET seating_config = \'{"sections": 10, "rows_per_section": 25, "seats_per_row": 20}\' WHERE seating_config IS NULL'
    )

    # Add server default for future inserts
    op.alter_column('event', 'venue_name', server_default='Default Venue')
    op.alter_column(
        'event',
        'seating_config',
        server_default='{"sections": 10, "rows_per_section": 25, "seats_per_row": 20}',
    )


def downgrade() -> None:
    """Remove default values."""
    # Remove server defaults
    op.alter_column('event', 'venue_name', server_default=None)
    op.alter_column('event', 'seating_config', server_default=None)
