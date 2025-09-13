"""add_performance_indexes

Revision ID: 7df8a81f1af9
Revises: 41849eb09de2
Create Date: 2025-09-13 15:57:55.501894

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7df8a81f1af9'
down_revision: Union[str, Sequence[str], None] = '41849eb09de2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Order table indexes for performance optimization
    op.create_index('idx_order_buyer_id', 'order', ['buyer_id'])
    op.create_index('idx_order_seller_id', 'order', ['seller_id'])
    op.create_index('idx_order_status', 'order', ['status'])
    op.create_index('idx_order_event_id', 'order', ['event_id'])
    op.create_index('idx_order_buyer_status', 'order', ['buyer_id', 'status'])
    op.create_index('idx_order_seller_status', 'order', ['seller_id', 'status'])

    # Event table indexes
    op.create_index('idx_event_seller_id', 'event', ['seller_id'])
    op.create_index('idx_event_status', 'event', ['status'])
    op.create_index('idx_event_is_active', 'event', ['is_active'])
    op.create_index('idx_event_active_status', 'event', ['is_active', 'status'])


def downgrade() -> None:
    # Drop order table indexes
    op.drop_index('idx_order_buyer_id', 'order')
    op.drop_index('idx_order_seller_id', 'order')
    op.drop_index('idx_order_status', 'order')
    op.drop_index('idx_order_event_id', 'order')
    op.drop_index('idx_order_buyer_status', 'order')
    op.drop_index('idx_order_seller_status', 'order')

    # Drop event table indexes
    op.drop_index('idx_event_seller_id', 'event')
    op.drop_index('idx_event_status', 'event')
    op.drop_index('idx_event_is_active', 'event')
    op.drop_index('idx_event_active_status', 'event')
