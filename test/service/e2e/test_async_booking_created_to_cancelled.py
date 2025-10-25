"""
E2E Test: Complete Async Booking Flow

Tests the full async booking workflow from creation to cancellation:
1. POST /api/booking creates booking with status='processing'
2. MQ consumer processes seat reservation asynchronously
3. GET /api/booking/{id} returns status='pending_payment' after processing
4. PATCH /api/booking/{id} cancels booking and releases seats
"""

import time
from typing import Any, Dict, Optional
import uuid
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

from test.test_constants import TEST_EVENT_ID_1
from test.util_constant import DEFAULT_PASSWORD


# Test Configuration Constants
BASE_URL = 'http://0.0.0.0:8000'
MQ_PROCESSING_WAIT_TIME = 5  # seconds to wait for MQ processing

# Event Configuration
EVENT_CONFIG = {
    'name': 'E2E Test Concert',
    'description': 'Testing async booking flow',
    'venue_name': 'Test Arena',
    'is_active': True,
    'seating_config': {
        'sections': [
            {
                'name': 'A',
                'price': 2000,
                'subsections': [{'number': 1, 'rows': 10, 'seats_per_row': 10}],
            },
            {
                'name': 'B',
                'price': 1500,
                'subsections': [{'number': 1, 'rows': 10, 'seats_per_row': 10}],
            },
        ]
    },
}


def create_manual_booking_config(event_id: UUID, seat_positions: list[str]) -> Dict[str, Any]:
    """Create booking configuration for manual seat selection"""
    return {
        'event_id': event_id,
        'section': 'B',
        'subsection': 1,
        'seat_selection_mode': 'manual',
        'seat_positions': seat_positions,
        'quantity': len(seat_positions),
    }


def create_best_available_booking_config(event_id: UUID, quantity: int) -> Dict[str, Any]:
    """Create booking configuration for best available seat selection"""
    return {
        'event_id': event_id,
        'section': 'A',
        'subsection': 1,
        'seat_selection_mode': 'best_available',
        'quantity': quantity,
    }


class BookingFlow:
    """Fluent interface for booking flow operations"""

    def __init__(self, client: httpx.AsyncClient, event_id: UUID):
        self.client = client
        self.event_id = TEST_EVENT_ID_1
        self.booking: Optional[Dict[str, Any]] = None

    async def create_best_available(self, *, quantity: int):
        """Create booking with best available seat selection"""
        config = create_best_available_booking_config(self.event_id, quantity)
        self.booking = await self._create_booking(config)
        return self

    async def create_manual(self, *, seat_positions: list[str]):
        """Create booking with manual seat selection"""
        config = create_manual_booking_config(self.event_id, seat_positions)
        self.booking = await self._create_booking(config)
        return self

    async def wait_for_processing(self, *, expected_status: str = 'pending_payment'):
        """Wait for MQ processing and verify expected status"""
        assert self.booking is not None, 'Booking must be created before waiting for processing'
        await self._wait_for_mq_processing()
        self.booking = await self._verify_booking_status(self.booking['id'], expected_status)
        return self

    async def verify_seat_count(self, *, expected_count: int):
        """Verify the booking has expected number of seats"""
        assert self.booking is not None, 'Booking must exist to verify seat count'
        assert len(self.booking['seat_positions']) == expected_count, (
            f'Expected {expected_count} seats, got {len(self.booking["seat_positions"])}'
        )
        return self

    async def cancel(self):
        """Cancel booking and wait for completion"""
        assert self.booking is not None, 'Booking must exist to cancel'
        await self._cancel_booking(self.booking['id'])
        await self._wait_for_mq_processing()
        self.booking = await self._verify_booking_status(self.booking['id'], 'cancelled')
        return self

    async def _create_booking(self, booking_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create booking and verify initial status"""
        response = await self.client.post(f'{BASE_URL}/api/booking', json=booking_config)
        assert response.status_code == 201, f'Booking creation failed: {response.text}'
        booking_data = response.json()
        assert booking_data['status'] == 'processing', (
            f"Expected status='processing', got '{booking_data['status']}'"
        )
        return booking_data

    async def _wait_for_mq_processing(self):
        """Wait for MQ consumer to process the operation"""
        time.sleep(MQ_PROCESSING_WAIT_TIME)

    async def _verify_booking_status(
        self, booking_id: UUID, expected_status: str
    ) -> Dict[str, Any]:
        """Get booking and verify it has expected status"""
        response = await self.client.get(f'{BASE_URL}/api/booking/{booking_id}')
        assert response.status_code == 200, f'Get booking failed: {response.text}'
        booking_data = response.json()
        assert booking_data['status'] == expected_status, (
            f"Expected status='{expected_status}', got '{booking_data['status']}'"
        )
        return booking_data

    async def _cancel_booking(self, booking_id: UUID):
        """Cancel booking and verify cancellation"""
        response = await self.client.patch(f'{BASE_URL}/api/booking/{booking_id}')
        assert response.status_code == 200, f'Booking cancellation failed: {response.text}'


@pytest.mark.e2e
class TestAsyncBookingFlow:
    """E2E tests for async booking flow requiring real HTTP server"""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_test_data(self):
        """Setup unique users and event for each test run"""
        await self._create_unique_test_users()
        await self._authenticate_users()
        await self._ensure_test_event_exists()

    async def _create_unique_test_users(self):
        """Create unique test users to avoid conflicts between test runs"""
        test_id = str(uuid.uuid4())[:8]
        timestamp = int(time.time())

        self.seller_email = f'seller_{test_id}_{timestamp}@test.com'
        self.buyer_email = f'buyer_{test_id}_{timestamp}@test.com'

        async with httpx.AsyncClient() as client:
            await self._create_or_get_user(
                client=client, email=self.seller_email, name='Test Seller', role='seller'
            )
            await self._create_or_get_user(
                client=client, email=self.buyer_email, name='Test Buyer', role='buyer'
            )

    async def _authenticate_users(self):
        """Login both users and store their authentication tokens"""
        # Authenticate seller
        seller_data = await self._login_user(self.seller_email, 'seller')
        self.seller_token = seller_data['token']
        self.seller_user_data = seller_data['user_data']

        # Authenticate buyer
        buyer_data = await self._login_user(self.buyer_email, 'buyer')
        self.buyer_token = buyer_data['token']

    async def _ensure_test_event_exists(self):
        """Get existing event_id=1 or create it for testing"""
        async with httpx.AsyncClient() as client:
            client.cookies.set('fastapiusersauth', self.seller_token)
            self.event_id = TEST_EVENT_ID_1

    async def _login_user(self, email: str, expected_role: str) -> Dict[str, Any]:
        """Login user and return user data with token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'{BASE_URL}/api/user/login', json={'email': email, 'password': DEFAULT_PASSWORD}
            )

            assert response.status_code == 200, f'Login failed for {email}: {response.text}'
            user_data = response.json()

            # Verify role
            assert user_data['role'] == expected_role, (
                f'Expected {expected_role} role, got {user_data["role"]}'
            )

            # Extract authentication token
            assert 'fastapiusersauth' in response.cookies, 'Login should set auth cookie'
            token = response.cookies['fastapiusersauth']

            return {'user_data': user_data, 'token': token}

    async def _get_or_create_event(self, client: httpx.AsyncClient) -> int:
        """Get existing event_id=1 or create it to avoid duplicates"""
        # Try to get existing event
        try:
            response = await client.get(f'{BASE_URL}/api/event/1')
            if response.status_code == 200:
                event_data = response.json()
                return event_data['id']
        except Exception:
            pass

        # Create new event
        response = await client.post(f'{BASE_URL}/api/event', json=EVENT_CONFIG)

        assert response.status_code == 201, f'Event creation failed: {response.text}'
        event_id = response.json()['id']
        return event_id

    async def _create_or_get_user(
        self, *, client: httpx.AsyncClient, email: str, name: str, role: str
    ) -> bool:
        """Create user or handle gracefully if already exists"""
        response = await client.post(
            f'{BASE_URL}/api/user',
            json={
                'email': email,
                'password': DEFAULT_PASSWORD,
                'name': name,
                'role': role,
            },
        )

        if response.status_code == 201:
            return True
        elif response.status_code == 500:
            return False
        else:
            raise AssertionError(
                f'Unexpected error creating user {email}: {response.status_code} - {response.text}'
            )

    @pytest.mark.asyncio
    async def test_booking_async_flow_with_manual_selection(self):
        """
        Test async booking flow with manual seat selection:
        1. Create booking → status='processing'
        2. Wait for MQ processing → status='pending_payment'
        3. Cancel booking → status='cancelled' and seats released
        """
        async with httpx.AsyncClient() as client:
            # Set buyer authentication
            client.cookies.set('fastapiusersauth', self.buyer_token)

            # Generate unique seat positions to avoid conflicts
            seat_base = int(time.time()) % 10 + 1
            seat_positions = [f'{seat_base}-1', f'{seat_base}-2']

            # Execute booking flow with fluent interface
            flow = BookingFlow(client, self.event_id)
            booking = await (
                await (
                    await flow.create_manual(seat_positions=seat_positions)
                ).wait_for_processing()
            ).cancel()

            assert booking.booking is not None
            assert booking.booking['status'] == 'cancelled'

    @pytest.mark.asyncio
    async def test_booking_async_flow_with_best_available(self):
        """
        Test async booking flow with best available seat selection:
        1. Create booking → status='processing'
        2. Wait for MQ processing → status='pending_payment'
        3. Cancel booking → status='cancelled' and seats released
        """
        async with httpx.AsyncClient() as client:
            # Set buyer authentication
            client.cookies.set('fastapiusersauth', self.buyer_token)

            # Execute booking flow with fluent interface
            flow = BookingFlow(client, self.event_id)
            booking = await (
                await (
                    await (await flow.create_best_available(quantity=3)).wait_for_processing()
                ).verify_seat_count(expected_count=3)
            ).cancel()

            assert booking.booking is not None
            assert booking.booking['status'] == 'cancelled'
