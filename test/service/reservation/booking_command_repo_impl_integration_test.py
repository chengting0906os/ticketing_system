"""
Integration tests for Reservation Service's BookingCommandRepoImpl

Tests the PostgreSQL operations for booking creation and ticket management.
"""

from typing import Any

from fastapi.testclient import TestClient
import pytest
import uuid_utils as uuid
from uuid_utils import UUID

from src.platform.constant.route_constant import EVENT_BASE
from src.service.shared_kernel.domain.value_object import BookingStatus
from src.service.reservation.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl,
)
from test.bdd_conftest.shared_step_utils import create_user, login_user
from test.constants import DEFAULT_PASSWORD, TEST_SELLER_EMAIL, TEST_SELLER_NAME


@pytest.mark.integration
class TestCreateBookingWithTicketsDirectly:
    """Test create_booking_and_update_tickets_to_reserved with real database"""

    @pytest.fixture
    def repo(self) -> BookingCommandRepoImpl:
        """Repository instance"""
        return BookingCommandRepoImpl()

    @pytest.fixture
    def booking_id(self) -> UUID:
        """Generate unique booking ID for each test"""
        return uuid.uuid7()

    @pytest.fixture
    def test_event_with_tickets(self, client: TestClient) -> dict[str, int]:
        # Create seller user
        create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
        login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)

        # Create event with seating config (automatically creates tickets)
        seating_config = {
            'rows': 3,
            'cols': 10,
            'sections': [
                {
                    'name': 'A',
                    'price': 1500,
                    'subsections': 1,
                }
            ],
        }
        response = client.post(
            EVENT_BASE,
            json={
                'name': 'Test Event for Repo Integration',
                'description': 'Testing repository idempotency',
                'venue_name': 'Test Venue',
                'seating_config': seating_config,
                'is_active': True,
            },
        )
        assert response.status_code == 201
        event_data = response.json()

        return {'event_id': event_data['id'], 'total_seats': 30, 'ticket_price': 1500}

    @pytest.mark.asyncio
    async def test_idempotency_returns_existing_booking_when_duplicate(
        self,
        repo: BookingCommandRepoImpl,
        booking_id: UUID,
        test_event_with_tickets: dict[str, Any],
    ) -> None:
        """
        Idempotency: Duplicate Kafka events should return existing booking.
        """
        # Given: Create initial booking
        first_result = await repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],
            total_price=3000,
        )

        first_booking = first_result['booking']
        first_tickets = first_result['tickets']

        assert first_booking.id == booking_id
        assert first_booking.status == BookingStatus.PENDING_PAYMENT
        assert len(first_tickets) == 2

        # When: Call again with same booking_id (simulating duplicate Kafka event)
        second_result = await repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,  # Same ID!
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],
            total_price=3000,
        )

        second_booking = second_result['booking']
        second_tickets = second_result['tickets']

        # Then: Should return existing booking (idempotent behavior)
        assert second_booking.id == first_booking.id
        assert second_booking.status == BookingStatus.PENDING_PAYMENT
        assert second_booking.total_price == 3000
        assert second_booking.created_at == first_booking.created_at  # Same timestamp!

        # Then: Should return same tickets
        assert len(second_tickets) == 2
        assert {t.id for t in second_tickets} == {t.id for t in first_tickets}

    @pytest.mark.asyncio
    async def test_creates_booking_and_updates_tickets_atomically(
        self,
        repo: BookingCommandRepoImpl,
        booking_id: UUID,
        test_event_with_tickets: dict[str, Any],
    ) -> None:
        """
        Atomicity: Booking creation and ticket update happen in single transaction.
        """
        # When: Create booking with tickets
        result = await repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2', '1-3'],
            total_price=4500,
        )

        booking = result['booking']
        tickets = result['tickets']

        # Then: Booking created correctly
        assert booking.id == booking_id
        assert booking.buyer_id == 2
        assert booking.event_id == test_event_with_tickets['event_id']
        assert booking.section == 'A'
        assert booking.subsection == 1
        assert booking.quantity == 3
        assert booking.total_price == 4500
        assert booking.status == BookingStatus.PENDING_PAYMENT
        assert booking.seat_positions == ['1-1', '1-2', '1-3']
        assert booking.seat_selection_mode == 'manual'
        assert booking.created_at is not None
        assert booking.updated_at is not None
        assert booking.paid_at is None

        # Then: Tickets updated correctly
        assert len(tickets) == 3
        for ticket in tickets:
            assert ticket.buyer_id == 2
            assert ticket.status.value == 'reserved'
            assert ticket.reserved_at is not None
            assert ticket.price == 1500

    @pytest.mark.asyncio
    async def test_returns_dict_with_booking_and_tickets(
        self,
        repo: BookingCommandRepoImpl,
        booking_id: UUID,
        test_event_with_tickets: dict[str, Any],
    ) -> None:
        """
        Return format: Dict with 'booking' and 'tickets' keys.
        """
        # When
        result = await repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1'],
            total_price=1500,
        )

        # Then: Returns dict with correct keys
        assert isinstance(result, dict)
        assert 'booking' in result
        assert 'tickets' in result
        assert result['booking'] is not None
        assert isinstance(result['tickets'], list)


@pytest.mark.integration
class TestUpdateStatusToCancelledAndReleaseTickets:
    """Test update_status_to_cancelled_and_release_tickets with idempotency"""

    @pytest.fixture
    def repo(self) -> BookingCommandRepoImpl:
        return BookingCommandRepoImpl()

    @pytest.fixture
    def booking_id(self) -> UUID:
        return uuid.uuid7()

    @pytest.fixture
    def test_event_with_tickets(self, client: TestClient) -> dict[str, int]:
        create_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD, TEST_SELLER_NAME, 'seller')
        login_user(client, TEST_SELLER_EMAIL, DEFAULT_PASSWORD)

        seating_config = {
            'rows': 3,
            'cols': 10,
            'sections': [{'name': 'A', 'price': 1500, 'subsections': 1}],
        }
        response = client.post(
            EVENT_BASE,
            json={
                'name': 'Test Event for Cancel',
                'description': 'Testing cancellation',
                'venue_name': 'Test Venue',
                'seating_config': seating_config,
                'is_active': True,
            },
        )
        assert response.status_code == 201
        return {'event_id': response.json()['id']}

    @pytest.mark.asyncio
    async def test_idempotent_cancellation(
        self,
        repo: BookingCommandRepoImpl,
        booking_id: UUID,
        test_event_with_tickets: dict[str, Any],
    ) -> None:
        """
        Idempotency: Duplicate cancellation events should be no-op.
        """
        # Given: Create and then cancel a booking
        await repo.create_booking_and_update_tickets_to_reserved(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],
            total_price=3000,
        )

        # When: Cancel first time
        first_result = await repo.update_status_to_cancelled_and_release_tickets(
            booking_id=booking_id
        )
        assert first_result is not None
        assert first_result.status == BookingStatus.CANCELLED

        # When: Cancel again (duplicate event)
        second_result = await repo.update_status_to_cancelled_and_release_tickets(
            booking_id=booking_id
        )

        # Then: Should return existing cancelled booking without error
        assert second_result is not None
        assert second_result.status == BookingStatus.CANCELLED
        assert second_result.id == first_result.id

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_booking(
        self,
        repo: BookingCommandRepoImpl,
    ) -> None:
        """
        Non-existent booking: Returns None instead of raising error.
        """
        nonexistent_id = uuid.uuid7()
        result = await repo.update_status_to_cancelled_and_release_tickets(
            booking_id=nonexistent_id
        )
        assert result is None
