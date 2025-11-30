"""Unit tests for InitEventAndTicketsStateHandlerImpl

These are pure unit tests that mock Kvrocks client directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)


@pytest.mark.asyncio
async def test_pipeline_batch_operations():
    """Test that Pipeline is used for batch operations and JSON config is written"""
    handler = InitEventAndTicketsStateHandlerImpl()
    config = {
        'rows': 2,
        'cols': 3,
        'sections': [{'name': 'A', 'price': 100, 'subsections': 1}],
    }

    mock_client = MagicMock()
    mock_pipeline = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline
    mock_pipeline.execute = AsyncMock(return_value=[])
    mock_client.zcard = AsyncMock(return_value=1)
    mock_client.execute_command = AsyncMock(return_value=True)
    mock_client.set = AsyncMock(return_value=True)

    with patch(
        'src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl.kvrocks_client'
    ) as mock_kvrocks:
        mock_kvrocks.get_client.return_value = mock_client

        result = await handler.initialize_seats_from_config(event_id=1, seating_config=config)

        mock_client.pipeline.assert_called_once()
        mock_pipeline.execute.assert_called_once()
        assert mock_client.execute_command.called or mock_client.set.called
        assert result['success'] is True
        assert result['total_seats'] == 6


@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling when pipeline execution fails"""
    handler = InitEventAndTicketsStateHandlerImpl()
    config = {
        'rows': 2,
        'cols': 3,
        'sections': [{'name': 'A', 'price': 100, 'subsections': 1}],
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
