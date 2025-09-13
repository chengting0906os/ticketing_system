"""create_ticket_table

Revision ID: a0bf82d09f3b
Revises: cc204770957e
Create Date: 2025-09-13 16:34:56.552180

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0bf82d09f3b'
down_revision: Union[str, Sequence[str], None] = 'cc204770957e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ticket table."""
    op.create_table(
        'ticket',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=10), nullable=False),
        sa.Column('subsection', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('seat_number', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='available', nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('buyer_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['buyer_id'],
            ['user.id'],
        ),
        sa.ForeignKeyConstraint(
            ['event_id'],
            ['event.id'],
        ),
        sa.ForeignKeyConstraint(
            ['order_id'],
            ['order.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'event_id', 'section', 'subsection', 'row_number', 'seat_number', name='uq_ticket_seat'
        ),
    )

    # Create indexes for performance
    op.create_index('idx_ticket_event_id', 'ticket', ['event_id'])
    op.create_index('idx_ticket_status', 'ticket', ['status'])
    op.create_index('idx_ticket_event_section', 'ticket', ['event_id', 'section', 'subsection'])
    op.create_index('idx_ticket_buyer_id', 'ticket', ['buyer_id'])
    op.create_index('idx_ticket_order_id', 'ticket', ['order_id'])
    op.create_index(
        'idx_ticket_seat_lookup',
        'ticket',
        ['event_id', 'section', 'subsection', 'row_number', 'seat_number'],
    )


def downgrade() -> None:
    """Drop ticket table."""
    op.drop_index('idx_ticket_seat_lookup', 'ticket')
    op.drop_index('idx_ticket_order_id', 'ticket')
    op.drop_index('idx_ticket_buyer_id', 'ticket')
    op.drop_index('idx_ticket_event_section', 'ticket')
    op.drop_index('idx_ticket_status', 'ticket')
    op.drop_index('idx_ticket_event_id', 'ticket')
    op.drop_table('ticket')
