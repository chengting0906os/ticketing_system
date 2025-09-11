"""rename product table to event

Revision ID: 8917ff70228d
Revises: 6dd31a846219
Create Date: 2025-09-11 23:18:56.920000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8917ff70228d'
down_revision: Union[str, Sequence[str], None] = '6dd31a846219'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # First, rename the product table to event
    op.rename_table('product', 'event')

    # Rename the sequence
    op.execute('ALTER SEQUENCE IF EXISTS product_id_seq RENAME TO event_id_seq')

    # Rename the foreign key constraint in the order table
    op.drop_constraint('order_product_id_fkey', 'order', type_='foreignkey')

    # Rename the column in the order table
    op.alter_column('order', 'product_id', new_column_name='event_id')

    # Create new foreign key constraint
    op.create_foreign_key('order_event_id_fkey', 'order', 'event', ['event_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the foreign key constraint
    op.drop_constraint('order_event_id_fkey', 'order', type_='foreignkey')

    # Rename the column back
    op.alter_column('order', 'event_id', new_column_name='product_id')

    # Rename the sequence back
    op.execute('ALTER SEQUENCE IF EXISTS event_id_seq RENAME TO product_id_seq')

    # Rename the table back
    op.rename_table('event', 'product')

    # Recreate the original foreign key constraint
    op.create_foreign_key('order_product_id_fkey', 'order', 'product', ['product_id'], ['id'])
