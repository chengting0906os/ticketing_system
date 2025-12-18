from typing import Any

from fastapi.testclient import TestClient
import pytest
import uuid_utils as uuid
from uuid_utils import UUID

from src.platform.constant.route_constant import EVENT_BASE
from src.service.ticketing.domain.entity.booking_entity import BookingStatus
from src.service.ticketing.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl,
)
from test.bdd_conftest.shared_step_utils import create_user, login_user
from test.constants import DEFAULT_PASSWORD, TEST_SELLER_EMAIL, TEST_SELLER_NAME


@pytest.mark.integration
class TestCreateBookingWithTicketsDirectly:
    """Test create_booking_with_tickets_directly with real database"""

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
        # Section A, 1 subsection, 3 rows × 10 seats = 30 tickets @ 1500 each
        # Compact format: rows/cols at top level, subsections as integer count
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
        # Given: Create initial booking
        first_result = await repo.create_booking_with_tickets_directly(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],
            seat_prices={'1-1': 1500, '1-2': 1500},
            total_price=3000,
        )

        first_booking = first_result['booking']
        first_tickets = first_result['tickets']

        assert first_booking.id == booking_id
        assert first_booking.status == BookingStatus.PENDING_PAYMENT
        assert len(first_tickets) == 2

        # When: Call again with same booking_id (simulating duplicate Kafka event)
        second_result = await repo.create_booking_with_tickets_directly(
            booking_id=booking_id,  # Same ID!
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2'],
            seat_prices={'1-1': 1500, '1-2': 1500},
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
        # When: Create booking with tickets
        result = await repo.create_booking_with_tickets_directly(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1', '1-2', '1-3'],
            seat_prices={'1-1': 1500, '1-2': 1500, '1-3': 1500},
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
        # When
        result = await repo.create_booking_with_tickets_directly(
            booking_id=booking_id,
            buyer_id=2,
            event_id=test_event_with_tickets['event_id'],
            section='A',
            subsection=1,
            seat_selection_mode='manual',
            reserved_seats=['1-1'],
            seat_prices={'1-1': 1500},
            total_price=1500,
        )

        # Then: Returns dict with correct keys
        assert isinstance(result, dict)
        assert 'booking' in result
        assert 'tickets' in result
        assert result['booking'] is not None
        assert isinstance(result['tickets'], list)
