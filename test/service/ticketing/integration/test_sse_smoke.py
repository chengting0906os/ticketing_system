from datetime import datetime, timezone

from anyio import fail_after, move_on_after
import pytest
import uuid_utils as uuid
from uuid_utils import UUID

from src.platform.event.in_memory_broadcaster import InMemoryEventBroadcasterImpl


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sse_realtime_broadcast_smoke():
    """
    Smoke test: Verify broadcaster delivers events to subscribers

    Flow:
    1. Create broadcaster (simulates DI container)
    2. Subscribe to booking_id (simulates SSE endpoint)
    3. Broadcast event (simulates Use Case after Kafka message)
    4. Verify subscriber receives event within 100ms
    """

    # Arrange: Create broadcaster and booking ID
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_id = UUID(str(uuid.uuid7()))

    # Act: Subscribe to booking updates (like SSE endpoint would)
    stream = await broadcaster.subscribe(booking_id=booking_id)

    # Simulate Use Case broadcasting event after DB update
    event_data = {
        'event_type': 'status_update',
        'booking_id': str(booking_id),
        'status': 'pending_payment',
        'total_price': 500,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'tickets': [
            {
                'id': 1,
                'section': 'A',
                'subsection': 1,
                'row': 1,
                'seat_num': 3,
                'price': 250,
                'status': 'reserved',
                'seat_identifier': 'A-1-1-3',
            },
            {
                'id': 2,
                'section': 'A',
                'subsection': 1,
                'row': 1,
                'seat_num': 4,
                'price': 250,
                'status': 'reserved',
                'seat_identifier': 'A-1-1-4',
            },
        ],
    }

    await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

    # Assert: SSE endpoint receives event within 100ms (event-driven!)
    with fail_after(0.1):
        received_event = await stream.receive()

    # Verify event data integrity
    assert received_event['event_type'] == 'status_update'
    assert received_event['booking_id'] == str(booking_id)
    assert received_event['status'] == 'pending_payment'
    assert received_event['total_price'] == 500
    assert len(received_event['tickets']) == 2
    assert received_event['tickets'][0]['status'] == 'reserved'
    assert received_event['tickets'][1]['status'] == 'reserved'

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_subscribers_isolation_smoke():
    """
    Smoke test: Verify multiple SSE connections receive events independently

    Scenario: 2 buyers watching different bookings
    - Booking A gets status update
    - Only Booking A's subscriber receives the event
    - Booking B's subscriber doesn't receive anything
    """

    # Arrange
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_a = UUID(str(uuid.uuid7()))
    booking_b = UUID(str(uuid.uuid7()))

    # Subscribe both buyers
    stream_a = await broadcaster.subscribe(booking_id=booking_a)
    stream_b = await broadcaster.subscribe(booking_id=booking_b)

    # Act: Broadcast to Booking A only
    event_a = {
        'event_type': 'status_update',
        'booking_id': str(booking_a),
        'status': 'pending_payment',
        'total_price': 500,
    }

    await broadcaster.broadcast(booking_id=booking_a, event_data=event_a)

    # Assert: Only Booking A receives event
    with fail_after(0.1):
        received_a = await stream_a.receive()
        assert received_a['booking_id'] == str(booking_a)

    # Booking B should NOT receive anything (timeout after 0.1s)
    received_b = None
    with move_on_after(0.1):
        received_b = await stream_b.receive()
    assert received_b is None, "Booking B should not receive Booking A's event"

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_a, stream=stream_a)
    await broadcaster.unsubscribe(booking_id=booking_b, stream=stream_b)


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_broadcaster_memory_cleanup_smoke():
    # Arrange
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_id = UUID(str(uuid.uuid7()))

    # Subscribe and unsubscribe 10 times
    for _ in range(10):
        stream = await broadcaster.subscribe(booking_id=booking_id)
        await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)

    # Assert: Subscriber dict should be clean
    assert (
        booking_id not in broadcaster._subscribers or len(broadcaster._subscribers[booking_id]) == 0
    ), 'Broadcaster should clean up empty subscriber lists'


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_full_handling_smoke():
    # Arrange: Create broadcaster (stream buffer size is 10)
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_id = UUID(str(uuid.uuid7()))
    stream = await broadcaster.subscribe(booking_id=booking_id)

    # Act: Broadcast 15 events (stream buffer max is 10)
    for i in range(15):
        event_data = {'event_type': 'status_update', 'sequence': i}
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

    # Assert: Stream should have first 10 events (newer 5 dropped due to buffer full)
    # Verify we can receive 10 items
    received_items = []
    for _ in range(10):
        with fail_after(1.0):
            item = await stream.receive()
            received_items.append(item)

    assert len(received_items) == 10, f'Stream should have 10 events, got {len(received_items)}'

    # Verify: Stream has events 0-9 (events 10-14 were dropped)
    assert received_items[0]['sequence'] == 0, 'Stream should contain first 10 events (0-9)'
    assert received_items[9]['sequence'] == 9, 'Last event should be sequence 9'

    # No more items should be available
    received = None
    with move_on_after(0.1):
        received = await stream.receive()
    assert received is None, 'No more events should be available'

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)
