"""change_booking_id_to_uuid

Revision ID: 0003
Revises: 0002
Create Date: 2025-10-31

Changes:
- Modify booking.id from VARCHAR(36) to UUID for native PostgreSQL UUID support
- Enable better storage efficiency (16 bytes vs 36 bytes)
- Maintain UUID7 generation in application layer
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: Change booking.id from VARCHAR(36) to UUID

    Migration strategy:
    1. Create new temporary UUID column
    2. Copy existing VARCHAR UUIDs (cast to UUID)
    3. Drop old column and constraints
    4. Rename new column to 'id'
    5. Add new primary key constraint
    """

    # Step 1: Add new column with UUID type
    op.add_column(
        'booking',
        sa.Column('id_new', UUID(as_uuid=True), nullable=True)
    )

    # Step 2: Copy existing VARCHAR UUIDs to new UUID column
    # Only copy if they are valid UUID format (skip invalid formats like "1", "2" from test data)
    op.execute(
        """
        UPDATE booking
        SET id_new = id::uuid
        WHERE id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        """
    )

    # Delete rows with invalid UUID format (old test data)
    op.execute(
        """
        DELETE FROM booking
        WHERE id_new IS NULL
        """
    )

    # Step 3: Make id_new NOT NULL after data migration
    op.alter_column('booking', 'id_new', nullable=False)

    # Step 4: Drop existing primary key constraint
    op.drop_constraint('booking_pkey', 'booking', type_='primary')

    # Step 5: Drop old VARCHAR column
    op.drop_column('booking', 'id')

    # Step 6: Rename new column to 'id'
    op.alter_column('booking', 'id_new', new_column_name='id')

    # Step 7: Add new primary key constraint
    op.create_primary_key('booking_pkey', 'booking', ['id'])


def downgrade() -> None:
    """
    Downgrade schema: Revert booking.id from UUID back to VARCHAR(36)
    """

    # Step 1: Add temporary VARCHAR column
    op.add_column(
        'booking',
        sa.Column('id_old', sa.String(length=36), nullable=True)
    )

    # Step 2: Convert UUID back to VARCHAR
    op.execute(
        """
        UPDATE booking
        SET id_old = id::varchar
        """
    )

    # Step 3: Make id_old NOT NULL
    op.alter_column('booking', 'id_old', nullable=False)

    # Step 4: Drop existing primary key
    op.drop_constraint('booking_pkey', 'booking', type_='primary')

    # Step 5: Drop UUID column
    op.drop_column('booking', 'id')

    # Step 6: Rename old column back to 'id'
    op.alter_column('booking', 'id_old', new_column_name='id')

    # Step 7: Recreate primary key
    op.create_primary_key('booking_pkey', 'booking', ['id'])
