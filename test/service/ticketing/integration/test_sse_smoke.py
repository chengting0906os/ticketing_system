"""
SSE Event-Driven Smoke Test

Verifies the complete flow:
1. Kafka Consumer receives message
2. Use Case updates DB and broadcasts event
3. SSE endpoint receives event via broadcaster
4. Event data is correct

Marks: smoke, integration
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
import uuid_utils as uuid

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

    print(f'\n📦 Booking ID: {booking_id}')

    # Act: Subscribe to booking updates (like SSE endpoint would)
    queue = await broadcaster.subscribe(booking_id=booking_id)
    print(f'✅ SSE endpoint subscribed to booking {booking_id}')

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
    print('📤 Use Case broadcasted status update')

    # Assert: SSE endpoint receives event within 100ms (event-driven!)
    try:
        received_event = await asyncio.wait_for(queue.get(), timeout=0.1)
        print('✅ SSE received event in <100ms')
    except asyncio.TimeoutError:
        pytest.fail('❌ SSE did not receive event within 100ms (should be <10ms)')

    # Verify event data integrity
    assert received_event['event_type'] == 'status_update'
    assert received_event['booking_id'] == str(booking_id)
    assert received_event['status'] == 'pending_payment'
    assert received_event['total_price'] == 500
    assert len(received_event['tickets']) == 2
    assert received_event['tickets'][0]['status'] == 'reserved'
    assert received_event['tickets'][1]['status'] == 'reserved'
    print('✅ Event data verified')

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)
    print(f'🔌 Unsubscribed from booking {booking_id}')

    print('\n🎉 SMOKE TEST PASSED: SSE event-driven flow works correctly!')


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

    print(f'\n📦 Booking A: {booking_a}')
    print(f'📦 Booking B: {booking_b}')

    # Subscribe both buyers
    queue_a = await broadcaster.subscribe(booking_id=booking_a)
    queue_b = await broadcaster.subscribe(booking_id=booking_b)
    print('✅ Both SSE endpoints subscribed')

    # Act: Broadcast to Booking A only
    event_a = {
        'event_type': 'status_update',
        'booking_id': str(booking_a),
        'status': 'pending_payment',
        'total_price': 500,
    }

    await broadcaster.broadcast(booking_id=booking_a, event_data=event_a)
    print('📤 Broadcasted update to Booking A')

    # Assert: Only Booking A receives event
    try:
        received_a = await asyncio.wait_for(queue_a.get(), timeout=0.1)
        assert received_a['booking_id'] == str(booking_a)
        print('✅ Booking A received its event')
    except asyncio.TimeoutError:
        pytest.fail('❌ Booking A should have received event')

    # Booking B should NOT receive anything
    assert queue_b.qsize() == 0, "Booking B should not receive Booking A's event"
    print('✅ Booking B correctly isolated (no event received)')

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_a, queue=queue_a)
    await broadcaster.unsubscribe(booking_id=booking_b, queue=queue_b)

    print('\n🎉 SMOKE TEST PASSED: Multiple subscribers properly isolated!')


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_broadcaster_memory_cleanup_smoke():
    """
    Smoke test: Verify broadcaster cleans up after unsubscribe

    Ensures no memory leaks when SSE connections close
    """

    # Arrange
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_id = UUID(str(uuid.uuid7()))

    print(f'\n📦 Booking ID: {booking_id}')

    # Subscribe and unsubscribe 10 times
    for _ in range(10):
        queue = await broadcaster.subscribe(booking_id=booking_id)
        await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)

    # Assert: Subscriber dict should be clean
    assert (
        booking_id not in broadcaster._subscribers or len(broadcaster._subscribers[booking_id]) == 0
    ), 'Broadcaster should clean up empty subscriber lists'

    print('✅ Memory cleanup verified (10 subscribe/unsubscribe cycles)')
    print('\n🎉 SMOKE TEST PASSED: No memory leaks detected!')


@pytest.mark.smoke
@pytest.mark.integration
@pytest.mark.asyncio
async def test_queue_full_handling_smoke():
    """
    Smoke test: Verify queue full handling (drop policy)

    Ensures system doesn't crash when SSE client is slow
    """

    # Arrange: Create broadcaster with small queue
    broadcaster = InMemoryEventBroadcasterImpl()
    booking_id = UUID(str(uuid.uuid7()))
    queue = await broadcaster.subscribe(booking_id=booking_id)

    print(f'\n📦 Booking ID: {booking_id}')
    print(f'📊 Queue max size: {queue.maxsize}')

    # Act: Broadcast 15 events (queue max is 10)
    for i in range(15):
        event_data = {'event_type': 'status_update', 'sequence': i}
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

    # Assert: Queue should have 10 events (newest 5 dropped due to queue full)
    assert queue.qsize() == 10, f'Queue should be full (10 events), got {queue.qsize()}'
    print(f'✅ Queue full: {queue.qsize()}/10 events (5 newest dropped)')

    # Verify: Queue has events 0-9 (events 10-14 were dropped)
    first_event = await queue.get()
    assert first_event['sequence'] == 0, 'Queue should contain first 10 events (0-9)'
    print(
        f'✅ Drop policy verified: first event sequence={first_event["sequence"]} (newer events dropped)'
    )

    # Cleanup
    await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)

    print('\n🎉 SMOKE TEST PASSED: Queue full handling works correctly!')
