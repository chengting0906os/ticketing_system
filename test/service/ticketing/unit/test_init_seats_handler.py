"""Unit tests for InitEventAndTicketsStateHandlerImpl

These are pure unit tests that inject mock dependencies via constructor.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)


def _create_handler(
    *, mock_client: MagicMock, mock_row_block_mgr: MagicMock | None = None
) -> InitEventAndTicketsStateHandlerImpl:
    mock_kvrocks_client = MagicMock()
    mock_kvrocks_client.get_client.return_value = mock_client

    if mock_row_block_mgr is None:
        mock_row_block_mgr = MagicMock()
        mock_row_block_mgr.initialize_subsection = AsyncMock()

    return InitEventAndTicketsStateHandlerImpl(
        kvrocks_client=mock_kvrocks_client,
        row_block_manager=mock_row_block_mgr,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipeline_batch_operations() -> None:
    mock_pipeline = MagicMock()
    mock_pipeline.setbit = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(return_value=[])

    mock_client = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline
    mock_client.execute_command = AsyncMock(return_value=True)

    mock_row_block_mgr = MagicMock()
    mock_row_block_mgr.initialize_subsection = AsyncMock()

    handler = _create_handler(mock_client=mock_client, mock_row_block_mgr=mock_row_block_mgr)

    config = {
        'rows': 2,
        'cols': 3,
        'sections': [{'name': 'A', 'price': 100, 'subsections': 1}],
    }

    result = await handler.initialize_seats_from_config(event_id=1, seating_config=config)

    mock_client.pipeline.assert_called_once()
    mock_pipeline.execute.assert_called_once()
    mock_client.execute_command.assert_called_once()
    assert result['success'] is True
    assert result['total_seats'] == 6


@pytest.mark.unit
@pytest.mark.asyncio
async def test_error_handling() -> None:
    """Test that pipeline errors are caught and returned gracefully."""
    mock_pipeline = MagicMock()
    mock_pipeline.setbit = MagicMock(return_value=mock_pipeline)
    mock_pipeline.execute = AsyncMock(side_effect=Exception('Pipeline error'))

    mock_client = MagicMock()
    mock_client.pipeline.return_value = mock_pipeline

    handler = _create_handler(mock_client=mock_client)

    config = {
        'rows': 2,
        'cols': 3,
        'sections': [{'name': 'A', 'price': 100, 'subsections': 1}],
    }

    result = await handler.initialize_seats_from_config(event_id=1, seating_config=config)

    assert result['success'] is False
    assert result['total_seats'] == 0
    assert 'Pipeline error' in result['error']


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_config_error() -> None:
    """Test that empty config returns error without attempting operations."""
    mock_client = MagicMock()
    handler = _create_handler(mock_client=mock_client)

    empty_config = {'sections': []}

    result = await handler.initialize_seats_from_config(event_id=1, seating_config=empty_config)

    assert result['success'] is False
    assert result['total_seats'] == 0
    assert 'No seats generated' in result['error']
