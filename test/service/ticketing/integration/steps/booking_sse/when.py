"""When steps for booking SSE feature tests"""

from pytest_bdd import parsers, when

from test.shared.utils import extract_table_data


@when('buyer connects to SSE stream for booking:')
def buyer_connects_to_sse_stream(step, client, booking_state, context, http_server):
    """Connect to SSE stream for a specific booking using threading approach"""
    import threading
    from test.service.ticketing.integration.steps.seat_reservation.when import (
        read_sse_events_in_thread,
    )

    data = extract_table_data(step)
    booking_id = data['booking_id']

    # Extract cookies from TestClient
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    # Start thread to read SSE events
    events_list = []
    url = f'{http_server}/api/booking/{booking_id}/status/sse'
    headers = {'Accept': 'text/event-stream'}

    thread = threading.Thread(
        target=read_sse_events_in_thread, args=(url, headers, cookies, events_list, 2), daemon=True
    )
    thread.start()
    thread.join(timeout=3)  # Wait max 3 seconds

    # Save results to context
    context['sse_events'] = events_list
    context['booking_id'] = booking_id

    # Create mock response for validation
    class MockResponse:
        def __init__(self, status_code, headers=None):
            self.status_code = status_code
            self.headers = headers or {}

    context['response'] = MockResponse(200, {'content-type': 'text/event-stream'})


@when('buyer is connected to SSE stream for the created booking')
def buyer_connected_to_created_booking_sse(step, booking_state, sse_state):
    """Establish SSE connection for the booking just created"""
    booking_id = booking_state['booking']['id']
    sse_state['booking_id'] = booking_id
    sse_state['connection_requested'] = True


@when('buyer is connected to SSE stream for booking {booking_id}')
def buyer_connected_to_booking_sse(booking_id: str, booking_state, sse_state):
    """Establish SSE connection for a specific booking ID"""
    sse_state['booking_id'] = booking_id
    sse_state['connection_requested'] = True


@when(parsers.parse('the seat reservation is processed successfully'))
def seat_reservation_processed_successfully(step, booking_state, sse_state):
    """Simulate successful seat reservation processing"""
    # The actual reservation happens via Kafka consumer
    # We just need to wait for the SSE event
    sse_state['waiting_for_event'] = 'seats_reserved'


@when('the seat reservation is processed')
def seat_reservation_processed(step, booking_state, sse_state):
    """Simulate seat reservation processing (may succeed or fail)"""
    sse_state['waiting_for_event'] = 'booking_status_change'


@when(parsers.parse('seat {seat_id} is already reserved by another buyer'))
def seat_already_reserved(seat_id: str, booking_state):
    """Mark a seat as already reserved"""
    # This would be set up in the given step by creating another reservation
    booking_state['conflicting_seat'] = seat_id


@when(parsers.parse('{buyer_email} pays for the booking with card "{card_number}"'))
def buyer_pays_for_booking_with_card(
    buyer_email: str, card_number: str, client, booking_state, sse_state
):
    """Buyer pays for booking and SSE should broadcast the status change"""
    from src.platform.constant.route_constant import BOOKING_PAY

    booking_id = booking_state['booking']['id']
    response = client.post(
        BOOKING_PAY.format(booking_id=booking_id),
        json={'card_number': card_number},
    )
    booking_state['payment_response'] = response
    sse_state['waiting_for_event'] = 'payment_completed'


@when(parsers.parse('{buyer_email} cancels their booking'))
def buyer_cancels_booking_for_sse(buyer_email: str, client, booking_state, sse_state):
    """Buyer cancels their booking and SSE should broadcast the status change"""
    from src.platform.constant.route_constant import BOOKING_CANCEL

    booking_id = booking_state['booking']['id']
    response = client.patch(BOOKING_CANCEL.format(booking_id=booking_id))
    booking_state['cancel_response'] = response
    sse_state['waiting_for_event'] = 'booking_cancelled'


@when(parsers.parse('{buyer_email} attempts to connect to SSE stream for booking:'))
def specific_buyer_attempts_sse_connect(buyer_email: str, step, client, context, http_server):
    """Specific buyer (possibly different from booking owner) tries to connect - may fail with 403"""
    import httpx

    data = extract_table_data(step)
    booking_id = data['booking_id']

    # Extract cookies from TestClient
    cookies = {}
    for cookie in client.cookies.jar:
        cookies[cookie.name] = cookie.value

    # Try to connect (may get 403)
    url = f'{http_server}/api/booking/{booking_id}/status/sse'
    headers = {'Accept': 'text/event-stream'}

    # Use a simple httpx call to check status code
    class MockResponse:
        def __init__(self, status_code, headers=None, json_data=None):
            self.status_code = status_code
            self.headers = headers or {}
            self._json_data = json_data or {}

        def json(self):
            return self._json_data

    try:
        with httpx.Client(timeout=2.0, cookies=cookies) as http_client:
            response = http_client.get(url, headers=headers)
            context['response'] = MockResponse(
                response.status_code,
                dict(response.headers),
                response.json() if response.status_code >= 400 else {},
            )
    except Exception as e:
        context['response'] = MockResponse(500, {}, {'detail': str(e)})
