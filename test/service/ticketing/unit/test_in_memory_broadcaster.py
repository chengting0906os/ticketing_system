"""
Unit tests for InMemoryEventBroadcaster

Tests the in-memory pub/sub mechanism used to distribute
booking status events from Kafka consumers to SSE endpoints.
"""

import asyncio

import pytest
import uuid_utils as uuid
from uuid_utils import UUID

from src.platform.event.in_memory_broadcaster import InMemoryEventBroadcasterImpl


class TestInMemoryBroadcaster:
    @pytest.fixture
    def broadcaster(self):
        return InMemoryEventBroadcasterImpl()

    @pytest.fixture
    def booking_id(self) -> UUID:
        return uuid.uuid7()

    @pytest.fixture
    def event_data(self, booking_id):
        return {
            'event_type': 'status_update',
            'booking_id': booking_id,
            'status': 'pending_payment',
            'total_price': 500,
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
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_subscribe_returns_queue(self, broadcaster, booking_id):
        queue = await broadcaster.subscribe(booking_id=booking_id)

        assert isinstance(queue, asyncio.Queue)
        assert queue.maxsize == 10  # Default max size

    @pytest.mark.asyncio
    async def test_broadcast_to_single_subscriber(self, broadcaster, booking_id, event_data):
        # Subscribe
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # Verify event received
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == event_data

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self, broadcaster, booking_id, event_data):
        # Subscribe multiple times
        queue1 = await broadcaster.subscribe(booking_id=booking_id)
        queue2 = await broadcaster.subscribe(booking_id=booking_id)
        queue3 = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast once
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # All subscribers should receive the event
        received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
        received3 = await asyncio.wait_for(queue3.get(), timeout=1.0)

        assert received1 == event_data
        assert received2 == event_data
        assert received3 == event_data

    @pytest.mark.asyncio
    async def test_broadcast_to_wrong_booking_id(self, broadcaster, booking_id, event_data):
        other_booking_id = UUID(str(uuid.uuid7()))

        # Subscribe to booking_id
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast to different booking_id
        await broadcaster.broadcast(booking_id=other_booking_id, event_data=event_data)

        # Verify no event received
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_broadcast_with_no_subscribers(self, broadcaster, booking_id, event_data):
        # Should not raise any exception
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self, broadcaster, booking_id, event_data):
        # Subscribe
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Unsubscribe
        await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)

        # Broadcast should not reach unsubscribed queue
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_multiple(self, broadcaster, booking_id, event_data):
        queue1 = await broadcaster.subscribe(booking_id=booking_id)
        queue2 = await broadcaster.subscribe(booking_id=booking_id)

        # Unsubscribe first queue
        await broadcaster.unsubscribe(booking_id=booking_id, queue=queue1)

        # Broadcast
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # queue2 should still receive
        received = await asyncio.wait_for(queue2.get(), timeout=1.0)
        assert received == event_data

        # queue1 should not receive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue1.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_queue_full_drops_event(self, broadcaster, booking_id):
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Fill the queue (maxsize=10)
        for i in range(10):
            await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': i})

        # Verify queue is full
        assert queue.qsize() == 10

        # Broadcast one more (should be dropped)
        await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': 'dropped'})

        # Queue should still have 10 items (oldest)
        assert queue.qsize() == 10

        # Verify first item is still seq=0 (FIFO preserved)
        first = await queue.get()
        assert first['seq'] == 0

    @pytest.mark.asyncio
    async def test_multiple_bookings_isolated(self, broadcaster, event_data):
        booking_a = UUID(str(uuid.uuid7()))
        booking_b = UUID(str(uuid.uuid7()))

        queue_a = await broadcaster.subscribe(booking_id=booking_a)
        queue_b = await broadcaster.subscribe(booking_id=booking_b)

        # Broadcast to booking A
        await broadcaster.broadcast(booking_id=booking_a, event_data={'booking': 'A'})

        # Only queue_a should receive
        received_a = await asyncio.wait_for(queue_a.get(), timeout=1.0)
        assert received_a == {'booking': 'A'}

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue_b.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_auto_cleanup_empty_subscriber_list(self, broadcaster, booking_id):
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Verify booking_id in subscribers
        assert booking_id in broadcaster._subscribers

        # Unsubscribe
        await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)

        # Empty list should be removed
        assert booking_id not in broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_and_broadcast(self, broadcaster, booking_id, event_data):
        async def subscribe_worker():
            queue = await broadcaster.subscribe(booking_id=booking_id)
            received = await asyncio.wait_for(queue.get(), timeout=2.0)
            return received

        async def broadcast_worker():
            await asyncio.sleep(0.1)  # Slight delay
            await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # Run concurrently
        results = await asyncio.gather(
            subscribe_worker(), subscribe_worker(), subscribe_worker(), broadcast_worker()
        )

        # First 3 are subscribers, last is broadcaster (None)
        assert results[0] == event_data
        assert results[1] == event_data
        assert results[2] == event_data

    @pytest.mark.asyncio
    async def test_broadcast_multiple_events_fifo(self, broadcaster, booking_id):
        queue = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast multiple events
        for i in range(5):
            await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': i})

        # Verify FIFO order
        for i in range(5):
            received = await asyncio.wait_for(queue.get(), timeout=1.0)
            assert received['seq'] == i

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_queue(self, broadcaster, booking_id):
        fake_queue = asyncio.Queue()

        # Should not raise any exception
        await broadcaster.unsubscribe(booking_id=booking_id, queue=fake_queue)

    @pytest.mark.asyncio
    async def test_memory_cleanup_after_many_subscribe_unsubscribe(self, broadcaster):
        initial_size = len(broadcaster._subscribers)

        # Subscribe and unsubscribe 100 times
        for _ in range(100):
            booking_id = UUID(str(uuid.uuid7()))
            queue = await broadcaster.subscribe(booking_id=booking_id)
            await broadcaster.unsubscribe(booking_id=booking_id, queue=queue)

        # Subscriber dict should be clean
        final_size = len(broadcaster._subscribers)
        assert final_size == initial_size  # Should be 0 or close to initial
