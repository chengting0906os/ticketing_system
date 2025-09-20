"""initial_database_schema

Revision ID: 0c7da820d4e5
Revises:
Create Date: 2025-09-15 00:07:11.644134

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c7da820d4e5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create user table
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(10), nullable=False, server_default='buyer'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # Create event table
    op.create_table(
        'event',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('venue_name', sa.String(255), nullable=False),
        sa.Column('seating_config', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('status', sa.String(20), nullable=False, server_default='available'),
        sa.Column('seller_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['seller_id'],
            ['user.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create booking table
    op.create_table(
        'booking',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending_payment'),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['buyer_id'],
            ['user.id'],
        ),
        sa.ForeignKeyConstraint(
            ['seller_id'],
            ['user.id'],
        ),
        sa.ForeignKeyConstraint(
            ['event_id'],
            ['event.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create ticket table
    op.create_table(
        'ticket',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(10), nullable=False),
        sa.Column('subsection', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('seat_number', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='available'),
        sa.Column('booking_id', sa.Integer(), nullable=True),
        sa.Column('buyer_id', sa.Integer(), nullable=True),
        sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['event_id'],
            ['event.id'],
        ),
        sa.ForeignKeyConstraint(
            ['booking_id'],
            ['booking.id'],
        ),
        sa.ForeignKeyConstraint(
            ['buyer_id'],
            ['user.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'event_id', 'section', 'subsection', 'row_number', 'seat_number', name='uq_ticket_seat'
        ),
    )

    # Create indexes
    op.create_index('ix_ticket_event_id', 'ticket', ['event_id'])
    op.create_index('ix_ticket_status', 'ticket', ['status'])
    op.create_index('ix_ticket_buyer_id', 'ticket', ['buyer_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes if they exist
    try:
        op.drop_index('ix_ticket_buyer_id', 'ticket')
    except Exception:
        pass
    try:
        op.drop_index('ix_ticket_status', 'ticket')
    except Exception:
        pass
    try:
        op.drop_index('ix_ticket_event_id', 'ticket')
    except Exception:
        pass

    # Drop tables in reverse order
    op.drop_table('ticket', if_exists=True)
    op.drop_table('booking', if_exists=True)
    op.drop_table('event', if_exists=True)
    op.drop_table('user', if_exists=True)
