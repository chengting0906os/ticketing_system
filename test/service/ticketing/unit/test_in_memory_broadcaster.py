"""
Unit tests for InMemoryEventBroadcaster

Tests the in-memory pub/sub mechanism used to distribute
booking status events from Kafka consumers to SSE endpoints.
"""

from anyio import create_memory_object_stream, fail_after, move_on_after
from anyio.streams.memory import ClosedResourceError, MemoryObjectReceiveStream
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
    async def test_subscribe_returns_stream(self, broadcaster, booking_id):
        stream = await broadcaster.subscribe(booking_id=booking_id)

        assert isinstance(stream, MemoryObjectReceiveStream)

    @pytest.mark.asyncio
    async def test_broadcast_to_single_subscriber(self, broadcaster, booking_id, event_data):
        # Subscribe
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # Verify event received
        with fail_after(1.0):
            received = await stream.receive()
        assert received == event_data

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self, broadcaster, booking_id, event_data):
        # Subscribe multiple times
        stream1 = await broadcaster.subscribe(booking_id=booking_id)
        stream2 = await broadcaster.subscribe(booking_id=booking_id)
        stream3 = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast once
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # All subscribers should receive the event
        with fail_after(1.0):
            received1 = await stream1.receive()
            received2 = await stream2.receive()
            received3 = await stream3.receive()

        assert received1 == event_data
        assert received2 == event_data
        assert received3 == event_data

    @pytest.mark.asyncio
    async def test_broadcast_to_wrong_booking_id(self, broadcaster, booking_id, event_data):
        other_booking_id = UUID(str(uuid.uuid7()))

        # Subscribe to booking_id
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast to different booking_id
        await broadcaster.broadcast(booking_id=other_booking_id, event_data=event_data)

        # Verify no event received (timeout after 0.1s)
        received = None
        with move_on_after(0.1):
            received = await stream.receive()
        assert received is None

    @pytest.mark.asyncio
    async def test_broadcast_with_no_subscribers(self, broadcaster, booking_id, event_data):
        # Should not raise any exception
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_stream(self, broadcaster, booking_id, event_data):
        # Subscribe
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Unsubscribe
        await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)

        # Broadcast should not reach unsubscribed stream
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # Verify stream is closed (receive should raise ClosedResourceError)

        with pytest.raises(ClosedResourceError):
            await stream.receive()

    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_multiple(self, broadcaster, booking_id, event_data):
        stream1 = await broadcaster.subscribe(booking_id=booking_id)
        stream2 = await broadcaster.subscribe(booking_id=booking_id)

        # Unsubscribe first stream
        await broadcaster.unsubscribe(booking_id=booking_id, stream=stream1)

        # Broadcast
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # stream2 should still receive
        with fail_after(1.0):
            received = await stream2.receive()
        assert received == event_data

        # stream1 should be closed

        with pytest.raises(ClosedResourceError):
            await stream1.receive()

    @pytest.mark.asyncio
    async def test_stream_full_drops_event(self, broadcaster, booking_id):
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Fill the stream buffer (max_buffer_size=10)
        for i in range(10):
            await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': i})

        # Broadcast one more (should be dropped due to WouldBlock)
        await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': 'dropped'})

        # Verify we can receive the 10 items (not 11)
        received_items = []
        for _ in range(10):
            with fail_after(1.0):
                item = await stream.receive()
                received_items.append(item)

        # Verify first item is seq=0 (FIFO preserved)
        assert received_items[0]['seq'] == 0
        assert len(received_items) == 10

        # No more items should be available
        received = None
        with move_on_after(0.1):
            received = await stream.receive()
        assert received is None

    @pytest.mark.asyncio
    async def test_multiple_bookings_isolated(self, broadcaster, event_data):
        booking_a = UUID(str(uuid.uuid7()))
        booking_b = UUID(str(uuid.uuid7()))

        stream_a = await broadcaster.subscribe(booking_id=booking_a)
        stream_b = await broadcaster.subscribe(booking_id=booking_b)

        # Broadcast to booking A
        await broadcaster.broadcast(booking_id=booking_a, event_data={'booking': 'A'})

        # Only stream_a should receive
        with fail_after(1.0):
            received_a = await stream_a.receive()
        assert received_a == {'booking': 'A'}

        # stream_b should not receive
        received_b = None
        with move_on_after(0.1):
            received_b = await stream_b.receive()
        assert received_b is None

    @pytest.mark.asyncio
    async def test_auto_cleanup_empty_subscriber_list(self, broadcaster, booking_id):
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Verify booking_id in subscribers
        assert booking_id in broadcaster._subscribers

        # Unsubscribe
        await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)

        # Empty list should be removed
        assert booking_id not in broadcaster._subscribers

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_and_broadcast(self, broadcaster, booking_id, event_data):
        import anyio

        # Subscribe first
        stream1 = await broadcaster.subscribe(booking_id=booking_id)
        stream2 = await broadcaster.subscribe(booking_id=booking_id)
        stream3 = await broadcaster.subscribe(booking_id=booking_id)

        # Then broadcast
        await anyio.sleep(0.1)
        await broadcaster.broadcast(booking_id=booking_id, event_data=event_data)

        # All subscribers should receive the event
        with fail_after(2.0):
            received1 = await stream1.receive()
            received2 = await stream2.receive()
            received3 = await stream3.receive()

        assert received1 == event_data
        assert received2 == event_data
        assert received3 == event_data

    @pytest.mark.asyncio
    async def test_broadcast_multiple_events_fifo(self, broadcaster, booking_id):
        stream = await broadcaster.subscribe(booking_id=booking_id)

        # Broadcast multiple events
        for i in range(5):
            await broadcaster.broadcast(booking_id=booking_id, event_data={'seq': i})

        # Verify FIFO order
        for i in range(5):
            with fail_after(1.0):
                received = await stream.receive()
            assert received['seq'] == i

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_stream(self, broadcaster, booking_id):
        _, fake_stream = create_memory_object_stream[dict](max_buffer_size=10)

        # Should not raise any exception
        await broadcaster.unsubscribe(booking_id=booking_id, stream=fake_stream)

    @pytest.mark.asyncio
    async def test_memory_cleanup_after_many_subscribe_unsubscribe(self, broadcaster):
        initial_size = len(broadcaster._subscribers)

        # Subscribe and unsubscribe 100 times
        for _ in range(100):
            booking_id = UUID(str(uuid.uuid7()))
            stream = await broadcaster.subscribe(booking_id=booking_id)
            await broadcaster.unsubscribe(booking_id=booking_id, stream=stream)

        # Subscriber dict should be clean
        final_size = len(broadcaster._subscribers)
        assert final_size == initial_size  # Should be 0 or close to initial
