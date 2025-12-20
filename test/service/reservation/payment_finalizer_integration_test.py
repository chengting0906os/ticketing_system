"""
Integration tests for PaymentFinalizer

Tests seat payment finalization (RESERVED -> SOLD) against real Kvrocks.
"""

import os
import random
import time

import pytest
from src.service.reservation.driven_adapter.reservation_helper.payment_finalizer import (
    PaymentFinalizer,
)
from src.service.reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
import uuid_utils as uuid

from src.platform.config.di import container
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from test.kvrocks_test_client import kvrocks_test_client


_KEY_PREFIX = os.getenv('KVROCKS_KEY_PREFIX', 'test_')


def _make_key(key: str) -> str:
    return f'{_KEY_PREFIX}{key}'


@pytest.fixture
async def payment_finalizer() -> PaymentFinalizer:
    """Create payment finalizer with proper initialization"""
    await kvrocks_client.initialize()
    return container.payment_finalizer()


@pytest.fixture
async def seat_handler() -> SeatStateCommandHandlerImpl:
    """Create seat state command handler for reserving seats"""
    await kvrocks_client.initialize()
    return container.seat_state_command_handler()


@pytest.fixture
async def init_handler() -> InitEventAndTicketsStateHandlerImpl:
    """Create seat initialization handler"""
    await kvrocks_client.initialize()
    return InitEventAndTicketsStateHandlerImpl()


@pytest.fixture(scope='function')
def unique_event_id() -> int:
    """Generate unique event_id for test isolation"""
    return int(time.time() * 1000000) % 10000000 + random.randint(1, 9999)


class TestPaymentFinalizerIntegration:
    """Integration tests for PaymentFinalizer"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_finalize_payment_seat_a_2_2_11(
        self,
        payment_finalizer: PaymentFinalizer,
        seat_handler: SeatStateCommandHandlerImpl,
        init_handler: InitEventAndTicketsStateHandlerImpl,
        unique_event_id: int,
    ) -> None:
        """Test finalizing payment for seat A-2-2-11 (RESERVED -> SOLD)"""
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats with 20 seats per row (compact format)
        config = {
            'rows': 3,
            'cols': 20,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 2}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)

        # Reserve seat A-2-2-11 first

        booking_id = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=2,
            quantity=1,
            seat_ids=['2-11'],
        )

        # Verify seat is RESERVED (status=1)
        bf_key = _make_key(f'seats_bf:{event_id}:A-2')
        # offset = ((row-1) * cols + (seat-1)) * 2 = ((2-1)*20 + (11-1)) * 2 = 60
        status_before = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 60)
        assert status_before == [1], f'Seat should be RESERVED before finalize, got {status_before}'

        # When: Finalize payment (new format: seat_position='row-seat', section/subsection separate)
        result = await payment_finalizer.finalize_seat_payment(
            seat_position='2-11',
            event_id=event_id,
            section='A',
            subsection=2,
        )

        # Then: Should return success
        assert result is True

        # Verify seat is now SOLD (status=2)
        status_after = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 60)
        assert status_after == [2], f'Seat should be SOLD after finalize, got {status_after}'

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_finalize_payment_seat_a_1_1_5(
        self,
        payment_finalizer: PaymentFinalizer,
        seat_handler: SeatStateCommandHandlerImpl,
        init_handler: InitEventAndTicketsStateHandlerImpl,
        unique_event_id: int,
    ) -> None:
        """Test finalizing payment for seat A-1-1-5 (RESERVED -> SOLD)"""
        # Get sync client for verification
        client = kvrocks_test_client.connect()

        # Given: Initialize seats with 20 seats per row (compact format)
        config = {
            'rows': 2,
            'cols': 20,
            'sections': [{'name': 'A', 'price': 1000, 'subsections': 1}],
        }
        event_id = unique_event_id
        await init_handler.initialize_seats_from_config(event_id=event_id, seating_config=config)
        booking_id = str(uuid.uuid7())
        await seat_handler.reserve_seats_atomic(
            event_id=event_id,
            booking_id=booking_id,
            buyer_id=1,
            mode='manual',
            section='A',
            subsection=1,
            quantity=1,
            seat_ids=['1-5'],
        )

        # Verify seat is RESERVED (status=1)
        bf_key = _make_key(f'seats_bf:{event_id}:A-1')
        # offset = ((row-1) * cols + (seat-1)) * 2 = ((1-1)*20 + (5-1)) * 2 = 8
        status_before = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 8)
        assert status_before == [1], f'Seat should be RESERVED before finalize, got {status_before}'

        # When: Finalize payment (new format: seat_position='row-seat', section/subsection separate)
        result = await payment_finalizer.finalize_seat_payment(
            seat_position='1-5',
            event_id=event_id,
            section='A',
            subsection=1,
        )

        # Then: Should return success
        assert result is True

        # Verify seat is now SOLD (status=2)
        status_after = client.execute_command('BITFIELD', bf_key, 'GET', 'u2', 8)
        assert status_after == [2], f'Seat should be SOLD after finalize, got {status_after}'
