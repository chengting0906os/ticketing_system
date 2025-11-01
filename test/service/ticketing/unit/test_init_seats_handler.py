"""Unit tests for InitEventAndTicketsStateHandlerImpl

These are pure unit tests that mock Kvrocks client directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)


@pytest.mark.asyncio
async def test_timestamp_format():
    """Test that timestamp is correctly formatted as Unix timestamp string"""
    handler = InitEventAndTicketsStateHandlerImpl()
    config = {
        'sections': [
            {
                'name': 'A',
                'price': 100,
                'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 3}],
            }
        ]
    }

    mock_client = MagicMock()
    mock_pipeline = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline
    mock_pipeline.execute = AsyncMock(return_value=[])
    mock_client.zcard = AsyncMock(return_value=1)

    with patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl.kvrocks_client'
    ) as mock_kvrocks:
        mock_kvrocks.get_client.return_value = mock_client

        await handler.initialize_seats_from_config(event_id=1, seating_config=config)

        hset_calls = [c for c in mock_pipeline.hset.call_args_list if 'section_stats' in str(c)]
        assert len(hset_calls) > 0

        stats_call = hset_calls[0]
        mapping = stats_call.kwargs.get(
            'mapping', stats_call.args[1] if len(stats_call.args) > 1 else {}
        )

        assert 'updated_at' in mapping
        timestamp = mapping['updated_at']
        assert timestamp.isdigit()
        assert int(timestamp) > 0


@pytest.mark.asyncio
async def test_pipeline_batch_operations():
    """Test that Pipeline is used for batch operations"""
    handler = InitEventAndTicketsStateHandlerImpl()
    config = {
        'sections': [
            {
                'name': 'A',
                'price': 100,
                'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 3}],
            }
        ]
    }

    mock_client = MagicMock()
    mock_pipeline = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline
    mock_pipeline.execute = AsyncMock(return_value=[])
    mock_client.zcard = AsyncMock(return_value=1)

    with patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl.kvrocks_client'
    ) as mock_kvrocks:
        mock_kvrocks.get_client.return_value = mock_client

        result = await handler.initialize_seats_from_config(event_id=1, seating_config=config)

        mock_client.pipeline.assert_called_once()
        mock_pipeline.execute.assert_called_once()
        assert result['success'] is True
        assert result['total_seats'] == 6


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling when pipeline execution fails"""
    handler = InitEventAndTicketsStateHandlerImpl()
    config = {
        'sections': [
            {
                'name': 'A',
                'price': 100,
                'subsections': [{'number': 1, 'rows': 2, 'seats_per_row': 3}],
            }
        ]
    }

    mock_client = MagicMock()
    mock_pipeline = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline
    mock_pipeline.execute = AsyncMock(side_effect=Exception('Pipeline error'))

    with patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl.kvrocks_client'
    ) as mock_kvrocks:
        mock_kvrocks.get_client.return_value = mock_client

        result = await handler.initialize_seats_from_config(event_id=1, seating_config=config)

        assert result['success'] is False
        assert result['total_seats'] == 0
        assert 'Pipeline error' in result['error']


@pytest.mark.asyncio
async def test_empty_config_error():
    """Test handling of empty seating configuration"""
    handler = InitEventAndTicketsStateHandlerImpl()
    empty_config = {'sections': []}

    result = await handler.initialize_seats_from_config(event_id=1, seating_config=empty_config)

    assert result['success'] is False
    assert result['total_seats'] == 0
    assert 'No seats generated' in result['error']
