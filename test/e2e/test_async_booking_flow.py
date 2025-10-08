"""
E2E Test: Async Booking Flow with MQ Processing

Tests the complete async booking workflow:
1. POST /api/booking creates booking with status='processing'
2. MQ consumer processes seat reservation asynchronously
3. GET /api/booking/{id} returns status='pending_payment' after processing
"""

import time

import pytest
import requests

from test.util_constant import DEFAULT_PASSWORD, TEST_BUYER_EMAIL, TEST_SELLER_EMAIL


@pytest.mark.e2e
class TestAsyncBookingFlow:
    """E2E tests for async booking flow requiring real HTTP server"""

    BASE_URL = 'http://0.0.0.0:8000'

    def setup_method(self):
        """Setup test data before each test"""
        # Create seller
        response = requests.post(
            f'{self.BASE_URL}/api/user/register',
            json={
                'email': TEST_SELLER_EMAIL,
                'password': DEFAULT_PASSWORD,
                'name': 'Test Seller',
                'role': 'seller',
            },
        )
        assert response.status_code == 201, f'Seller creation failed: {response.text}'

        # Create buyer
        response = requests.post(
            f'{self.BASE_URL}/api/user/register',
            json={
                'email': TEST_BUYER_EMAIL,
                'password': DEFAULT_PASSWORD,
                'name': 'Test Buyer',
                'role': 'buyer',
            },
        )
        assert response.status_code == 201, f'Buyer creation failed: {response.text}'

        # Login as seller
        seller_login = requests.post(
            f'{self.BASE_URL}/api/user/login',
            json={'email': TEST_SELLER_EMAIL, 'password': DEFAULT_PASSWORD},
        )
        assert seller_login.status_code == 200
        self.seller_token = seller_login.json()['access_token']

        # Login as buyer
        buyer_login = requests.post(
            f'{self.BASE_URL}/api/user/login',
            json={'email': TEST_BUYER_EMAIL, 'password': DEFAULT_PASSWORD},
        )
        assert buyer_login.status_code == 200
        self.buyer_token = buyer_login.json()['access_token']

        # Create event
        event_response = requests.post(
            f'{self.BASE_URL}/api/event',
            headers={'Authorization': f'Bearer {self.seller_token}'},
            json={
                'name': 'E2E Test Concert',
                'description': 'Testing async booking',
                'venue_name': 'Test Arena',
                'is_active': True,
                'seating_config': {
                    'sections': [
                        {
                            'name': 'A',
                            'price': 2000,
                            'subsections': [{'number': 1, 'rows': 5, 'seats_per_row': 5}],
                        }
                    ]
                },
            },
        )
        assert event_response.status_code == 201, f'Event creation failed: {event_response.text}'
        self.event_id = event_response.json()['id']

    def test_booking_async_flow_with_manual_selection(self):
        """
        Test async booking flow with manual seat selection:
        1. Create booking → status='processing'
        2. Wait 5 seconds for MQ processing
        3. Check booking → status='pending_payment'
        """
        # Step 1: Create booking with manual seat selection
        create_response = requests.post(
            f'{self.BASE_URL}/api/booking',
            headers={'Authorization': f'Bearer {self.buyer_token}'},
            json={
                'event_id': self.event_id,
                'section': 'A',
                'subsection': 1,
                'seat_selection_mode': 'manual',
                'seat_positions': ['A-1-1-1', 'A-1-1-2'],
                'quantity': 2,
            },
        )

        assert create_response.status_code == 201, (
            f'Booking creation failed: {create_response.text}'
        )
        booking_data = create_response.json()
        booking_id = booking_data['id']

        # Verify initial status is 'processing'
        assert booking_data['status'] == 'processing', (
            f"Expected status='processing', got '{booking_data['status']}'"
        )

        print(f'✓ Booking {booking_id} created with status=processing')

        # Step 2: Wait for MQ consumer to process
        print('⏳ Waiting 5 seconds for MQ processing...')
        time.sleep(5)

        # Step 3: Check booking status
        get_response = requests.get(
            f'{self.BASE_URL}/api/booking/{booking_id}',
            headers={'Authorization': f'Bearer {self.buyer_token}'},
        )

        assert get_response.status_code == 200, f'Get booking failed: {get_response.text}'
        updated_booking = get_response.json()

        # Verify status changed to 'pending_payment'
        assert updated_booking['status'] == 'pending_payment', (
            f"Expected status='pending_payment', got '{updated_booking['status']}'. "
            'MQ consumer may not have processed the booking.'
        )

        print(f'✓ Booking {booking_id} status changed to pending_payment')

    def test_booking_async_flow_with_best_available(self):
        """
        Test async booking flow with best available seat selection:
        1. Create booking → status='processing'
        2. Wait 5 seconds for MQ processing
        3. Check booking → status='pending_payment'
        """
        # Step 1: Create booking with best available
        create_response = requests.post(
            f'{self.BASE_URL}/api/booking',
            headers={'Authorization': f'Bearer {self.buyer_token}'},
            json={
                'event_id': self.event_id,
                'section': 'A',
                'subsection': 1,
                'seat_selection_mode': 'best_available',
                'quantity': 3,
            },
        )

        assert create_response.status_code == 201, (
            f'Booking creation failed: {create_response.text}'
        )
        booking_data = create_response.json()
        booking_id = booking_data['id']

        assert booking_data['status'] == 'processing'
        print(f'✓ Booking {booking_id} created with status=processing')

        # Step 2: Wait for MQ consumer
        print('⏳ Waiting 5 seconds for MQ processing...')
        time.sleep(5)

        # Step 3: Verify status changed
        get_response = requests.get(
            f'{self.BASE_URL}/api/booking/{booking_id}',
            headers={'Authorization': f'Bearer {self.buyer_token}'},
        )

        assert get_response.status_code == 200
        updated_booking = get_response.json()

        assert updated_booking['status'] == 'pending_payment', (
            f"Expected 'pending_payment', got '{updated_booking['status']}'"
        )

        # Verify seat_positions were assigned
        assert len(updated_booking['seat_positions']) == 3, (
            f'Expected 3 seats, got {len(updated_booking["seat_positions"])}'
        )

        print(f'✓ Booking {booking_id} processed with seats: {updated_booking["seat_positions"]}')
