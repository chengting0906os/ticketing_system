"""
Unit tests for CreateEventAndTicketsUseCase - Kafka topics setup

Test focus:
1. Kafka topics/partitions are called after event creation
2. Kafka setup failure should not block event creation (fail-safe)
3. Verify call order: DB -> Kvrocks -> Kafka
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.domain.aggregate.event_ticketing_aggregate import (
    Event,
    EventTicketingAggregate,
)
from src.service.ticketing.domain.enum import EventStatus


class TestCreateEventKafkaSetup:
    """Test CreateEventAndTicketsUseCase Kafka topics setup"""

    @pytest.fixture
    def mock_event_repo(self):
        repo = MagicMock()
        repo.create_event_aggregate = AsyncMock()
        repo.create_event_aggregate_with_batch_tickets = AsyncMock()
        repo.update_event_aggregate = AsyncMock()
        repo.delete_event_aggregate = AsyncMock()
        return repo

    @pytest.fixture
    def mock_mq_orchestrator(self):
        orchestrator = MagicMock()
        orchestrator.setup_kafka_topics_and_partitions = AsyncMock()
        return orchestrator

    @pytest.fixture
    def mock_init_state_handler(self):
        handler = MagicMock()
        handler.initialize_seats_from_config = AsyncMock(
            return_value={'success': True, 'total_seats': 100, 'sections_count': 1}
        )
        return handler

    @pytest.fixture
    def use_case(self, mock_event_repo, mock_mq_orchestrator, mock_init_state_handler):
        return CreateEventAndTicketsUseCase(
            event_ticketing_command_repo=mock_event_repo,
            mq_infra_orchestrator=mock_mq_orchestrator,
            init_state_handler=mock_init_state_handler,
        )

    @pytest.fixture
    def valid_event_data(self):
        return {
            'name': 'Test Concert',
            'description': 'Test Description',
            'seller_id': 1,
            'venue_name': 'Test Venue',
            'seating_config': {
                'sections': [
                    {
                        'name': 'A',
                        'price': 1000,
                        'subsections': [{'number': 1, 'rows': 10, 'seats_per_row': 10}],
                    }
                ]
            },
            'is_active': True,
        }

    @pytest.fixture
    def created_aggregate(self, valid_event_data):
        event = Event(
            id=1,
            name='Test Concert',
            description='Test Description',
            seller_id=1,
            venue_name='Test Venue',
            seating_config=valid_event_data['seating_config'],
            status=EventStatus.OPEN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        aggregate = EventTicketingAggregate(event=event, tickets=[])
        return aggregate

    @pytest.mark.asyncio
    async def test_kafka_setup_called_after_event_creation(
        self,
        use_case,
        mock_event_repo,
        mock_mq_orchestrator,
        mock_init_state_handler,
        valid_event_data,
        created_aggregate,
    ):
        """Test that Kafka topics/partitions are called after event creation"""
        # Given: Track call order
        call_order = []

        async def track_create_event(*, event_aggregate):
            call_order.append('create_event')
            return created_aggregate

        async def track_batch_tickets(*, event_aggregate, ticket_tuples):
            call_order.append('batch_tickets')
            return created_aggregate

        async def track_init_seats(*, event_id, seating_config):
            call_order.append('init_seats')
            return {'success': True, 'total_seats': 100, 'sections_count': 1}

        async def track_update_event(*, event_aggregate):
            call_order.append('update_event')
            return created_aggregate

        async def track_kafka_setup(*, event_id, seating_config):
            call_order.append('kafka_setup')

        mock_event_repo.create_event_aggregate = AsyncMock(side_effect=track_create_event)
        mock_event_repo.create_event_aggregate_with_batch_tickets = AsyncMock(
            side_effect=track_batch_tickets
        )
        mock_init_state_handler.initialize_seats_from_config = AsyncMock(
            side_effect=track_init_seats
        )
        mock_event_repo.update_event_aggregate = AsyncMock(side_effect=track_update_event)
        mock_mq_orchestrator.setup_kafka_topics_and_partitions = AsyncMock(
            side_effect=track_kafka_setup
        )

        # When
        await use_case.create_event_and_tickets(**valid_event_data)

        # Then: Kafka setup should be called last
        assert call_order == [
            'create_event',
            'batch_tickets',
            'init_seats',
            'update_event',
            'kafka_setup',
        ]

    @pytest.mark.asyncio
    async def test_kafka_setup_failure_does_not_block_event_creation(
        self,
        use_case,
        mock_event_repo,
        mock_mq_orchestrator,
        valid_event_data,
        created_aggregate,
    ):
        """Test that Kafka setup failure does not block event creation (fail-safe)"""
        # Given: Kafka setup fails
        mock_event_repo.create_event_aggregate = AsyncMock(return_value=created_aggregate)
        mock_event_repo.create_event_aggregate_with_batch_tickets = AsyncMock(
            return_value=created_aggregate
        )
        mock_event_repo.update_event_aggregate = AsyncMock(return_value=created_aggregate)
        mock_mq_orchestrator.setup_kafka_topics_and_partitions = AsyncMock(
            side_effect=Exception('Kafka connection failed')
        )

        # When
        result = await use_case.create_event_and_tickets(**valid_event_data)

        # Then: Event should be created successfully
        assert result is not None
        assert result.event.id == 1

        # Kafka setup was attempted
        mock_mq_orchestrator.setup_kafka_topics_and_partitions.assert_called_once()

    @pytest.mark.asyncio
    async def test_kafka_setup_receives_correct_parameters(
        self,
        use_case,
        mock_event_repo,
        mock_mq_orchestrator,
        valid_event_data,
        created_aggregate,
    ):
        """Test that Kafka setup receives correct event_id and seating_config"""
        # Given
        mock_event_repo.create_event_aggregate = AsyncMock(return_value=created_aggregate)
        mock_event_repo.create_event_aggregate_with_batch_tickets = AsyncMock(
            return_value=created_aggregate
        )
        mock_event_repo.update_event_aggregate = AsyncMock(return_value=created_aggregate)

        # When
        await use_case.create_event_and_tickets(**valid_event_data)

        # Then: Kafka setup called with correct parameters
        mock_mq_orchestrator.setup_kafka_topics_and_partitions.assert_called_once_with(
            event_id=1, seating_config=valid_event_data['seating_config']
        )
