"""init_db_schema

Revision ID: 0001
Revises:
Create Date: 2025-12-06

Schema:
- user: User accounts (seller/buyer)
- event: Events with seating configuration and statistics
- booking: Booking records with UUID primary key
- ticket: Individual tickets
- subsection_stats: Subsection-level statistics table
- Automatic statistics update triggers

Note: seating_config uses compact format:
  {"rows": 10, "cols": 10, "sections": [{"name": "A", "price": 1000, "subsections": 1}]}
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables with final schema."""

    # ========== STEP 1: Create base tables ==========

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

    # Event table with stats column
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
        sa.Column(
            'stats',
            JSONB,
            nullable=False,
            server_default=sa.text("'{\"available\": 0, \"reserved\": 0, \"sold\": 0, \"total\": 0}'::jsonb"),
        ),  # Event-level statistics
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

    # ========== STEP 2: Create subsection_stats table ==========
    op.create_table(
        'subsection_stats',
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=10), nullable=False),
        sa.Column('subsection', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('available', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('reserved', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('sold', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('event_id', 'section', 'subsection'),
        sa.ForeignKeyConstraint(['event_id'], ['event.id'], ondelete='CASCADE'),
    )

    # ========== STEP 3: Initialize statistics from existing data ==========
    # Calculate and populate event-level stats
    op.execute("""
        UPDATE event e
        SET stats = (
            SELECT jsonb_build_object(
                'available', COALESCE(SUM(CASE WHEN t.status = 'available' THEN 1 ELSE 0 END), 0),
                'reserved', COALESCE(SUM(CASE WHEN t.status = 'reserved' THEN 1 ELSE 0 END), 0),
                'sold', COALESCE(SUM(CASE WHEN t.status = 'sold' THEN 1 ELSE 0 END), 0),
                'total', COALESCE(COUNT(*), 0),
                'updated_at', EXTRACT(EPOCH FROM NOW())::bigint
            )
            FROM ticket t
            WHERE t.event_id = e.id
        )
    """)

    # Calculate and populate subsection-level stats
    op.execute("""
        INSERT INTO subsection_stats (event_id, section, subsection, price, available, reserved, sold, updated_at)
        SELECT
            t.event_id,
            t.section,
            t.subsection,
            MAX(t.price) AS price,
            SUM(CASE WHEN t.status = 'available' THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN t.status = 'reserved' THEN 1 ELSE 0 END) AS reserved,
            SUM(CASE WHEN t.status = 'sold' THEN 1 ELSE 0 END) AS sold,
            EXTRACT(EPOCH FROM NOW())::bigint AS updated_at
        FROM ticket t
        GROUP BY t.event_id, t.section, t.subsection
        ON CONFLICT (event_id, section, subsection) DO NOTHING
    """)

    # ========== STEP 4: Load and apply trigger from external SQL file ==========
    # Trigger is maintained in src/platform/database/trigger/update_event_stats.sql
    trigger_sql_path = Path(__file__).parent.parent.parent / 'database' / 'trigger' / 'update_event_stats.sql'
    with open(trigger_sql_path, encoding='utf-8') as trigger_file:
        trigger_sql = trigger_file.read()
        op.execute(trigger_sql)


def downgrade() -> None:
    """Drop all tables and triggers in reverse order of creation."""

    # ========== STEP 4: Drop trigger and function ==========
    op.execute("DROP TRIGGER IF EXISTS ticket_status_change_trigger ON ticket;")
    op.execute("DROP FUNCTION IF EXISTS update_event_stats();")

    # ========== STEP 3 & 2: Drop subsection_stats table ==========
    op.drop_table('subsection_stats')

    # ========== STEP 1: Drop base tables (indexes dropped automatically) ==========
    op.drop_table('ticket')
    op.drop_table('booking')
    op.drop_table('event')
    op.drop_table('user')
