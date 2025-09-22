"""remove_seller_id_from_booking

Revision ID: abc123456790
Revises: 070c0eadd71e
Create Date: 2025-09-22 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abc123456790'
down_revision: Union[str, Sequence[str], None] = '070c0eadd71e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove seller_id column from booking table
    op.drop_column('booking', 'seller_id')


def downgrade() -> None:
    # Add seller_id column back to booking table
    op.add_column(
        'booking', sa.Column('seller_id', sa.INTEGER(), nullable=False, server_default='0')
    )
    # Add foreign key constraint back
    op.create_foreign_key('booking_seller_id_fkey', 'booking', 'user', ['seller_id'], ['id'])
