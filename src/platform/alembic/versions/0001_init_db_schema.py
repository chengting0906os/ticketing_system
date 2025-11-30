"""init_db_schema

Revision ID: 0001
Revises:
Create Date: 2025-11-30

Schema:
- user: User accounts (seller/buyer)
- event: Events with seating configuration (compact format)
- booking: Booking records with UUID primary key
- ticket: Individual tickets

Note: seating_config uses compact format:
  {"rows": 10, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]}
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables with final schema."""

    # User table
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)

    # Event table (seating_config uses compact format)
    op.create_table(
        'event',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('seller_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('venue_name', sa.String(length=255), nullable=False),
        sa.Column('seating_config', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ['seller_id'],
            ['user.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Booking table (UUID primary key)
    op.create_table(
        'booking',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=10), nullable=False),
        sa.Column('subsection', sa.Integer(), nullable=False),
        sa.Column('seat_positions', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('total_price', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('seat_selection_mode', sa.String(length=20), nullable=False),
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
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_booking_buyer_id'), 'booking', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_booking_event_id'), 'booking', ['event_id'], unique=False)

    # Ticket table
    op.create_table(
        'ticket',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=10), nullable=False),
        sa.Column('subsection', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('seat_number', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=True),
        sa.Column('reserved_at', sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'event_id', 'section', 'subsection', 'row_number', 'seat_number', name='uq_ticket_seat'
        ),
    )
    op.create_index(op.f('ix_ticket_event_id'), 'ticket', ['event_id'], unique=False)
    op.create_index(op.f('ix_ticket_buyer_id'), 'ticket', ['buyer_id'], unique=False)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index(op.f('ix_ticket_buyer_id'), table_name='ticket')
    op.drop_index(op.f('ix_ticket_event_id'), table_name='ticket')
    op.drop_table('ticket')
    op.drop_index(op.f('ix_booking_event_id'), table_name='booking')
    op.drop_index(op.f('ix_booking_buyer_id'), table_name='booking')
    op.drop_table('booking')
    op.drop_table('event')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
