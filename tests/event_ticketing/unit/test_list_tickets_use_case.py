"""Unit tests for ListTicketsUseCase."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.event_ticketing.domain.ticket_entity import Ticket, TicketStatus
from src.event_ticketing.use_case.list_tickets_use_case import ListTicketsUseCase
from src.shared.exception.exceptions import ForbiddenError, NotFoundError


class TestListTicketsUseCase:
    """Test cases for ListTicketsUseCase following TDD principles."""

    @pytest.fixture
    def mock_uow(self):
        """Mock unit of work for testing."""
        uow = Mock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        uow.events = Mock()
        uow.events.get_by_id = AsyncMock()
        uow.tickets = Mock()
        uow.tickets.get_by_event_id = AsyncMock()
        uow.tickets.get_available_tickets_by_event = AsyncMock()
        uow.tickets.get_by_event_and_section = AsyncMock()
        return uow

    @pytest.fixture
    def sample_event(self):
        """Sample event for testing."""
        return Mock(id=1, seller_id=1, name='Test Event')

    @pytest.fixture
    def sample_tickets(self):
        """Sample tickets for testing."""
        now = datetime.now()
        return [
            Ticket(
                id=1,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1000,
                status=TicketStatus.AVAILABLE,
                created_at=now,
                updated_at=now,
            ),
            Ticket(
                id=2,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=2,
                price=1000,
                status=TicketStatus.SOLD,
                created_at=now,
                updated_at=now,
            ),
        ]

    @pytest.fixture
    def available_tickets(self):
        """Sample available tickets for testing."""
        now = datetime.now()
        return [
            Ticket(
                id=1,
                event_id=1,
                section='A',
                subsection=1,
                row=1,
                seat=1,
                price=1000,
                status=TicketStatus.AVAILABLE,
                created_at=now,
                updated_at=now,
            )
        ]

    @pytest.mark.asyncio
    async def test_seller_can_list_all_tickets_for_their_event(
        self, mock_uow, sample_event, sample_tickets
    ):
        """Test that a seller can list all tickets (including sold ones) for their event."""
        # Given
        event_id = 1
        seller_id = 1
        mock_uow.events.get_by_id.return_value = sample_event
        mock_uow.tickets.get_by_event_id.return_value = sample_tickets

        use_case = ListTicketsUseCase(mock_uow)

        # When
        result = await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

        # Then
        assert len(result) == 2
        assert result == sample_tickets
        mock_uow.events.get_by_id.assert_called_once_with(event_id=event_id)
        mock_uow.tickets.get_by_event_id.assert_called_once_with(event_id=event_id)

    @pytest.mark.asyncio
    async def test_buyer_can_only_list_available_tickets(
        self, mock_uow, sample_event, available_tickets
    ):
        """Test that a buyer (seller_id=None) can only see available tickets."""
        # Given
        event_id = 1
        seller_id = None  # Indicates buyer access
        mock_uow.events.get_by_id.return_value = sample_event
        mock_uow.tickets.get_available_tickets_by_event.return_value = available_tickets

        use_case = ListTicketsUseCase(mock_uow)

        # When
        result = await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

        # Then
        assert len(result) == 1
        assert result == available_tickets
        mock_uow.events.get_by_id.assert_called_once_with(event_id=event_id)
        mock_uow.tickets.get_available_tickets_by_event.assert_called_once_with(event_id=event_id)

    @pytest.mark.asyncio
    async def test_seller_cannot_list_tickets_for_other_sellers_event(self, mock_uow, sample_event):
        """Test that a seller cannot list tickets for another seller's event."""
        # Given
        event_id = 1
        seller_id = 2  # Different seller
        other_seller_event = Mock(id=1, seller_id=1, name='Other Seller Event')
        mock_uow.events.get_by_id.return_value = other_seller_event

        use_case = ListTicketsUseCase(mock_uow)

        # When / Then
        with pytest.raises(ForbiddenError, match='Not authorized to view tickets for this event'):
            await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

    @pytest.mark.asyncio
    async def test_list_tickets_for_nonexistent_event(self, mock_uow):
        """Test error handling when event does not exist."""
        # Given
        event_id = 999
        seller_id = 1
        mock_uow.events.get_by_id.return_value = None

        use_case = ListTicketsUseCase(mock_uow)

        # When / Then
        with pytest.raises(NotFoundError, match='Event not found'):
            await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

    @pytest.mark.asyncio
    async def test_seller_can_list_tickets_by_section(self, mock_uow, sample_event, sample_tickets):
        """Test that a seller can list tickets for specific section of their event."""
        # Given
        event_id = 1
        section = 'A'
        subsection = 1
        seller_id = 1
        mock_uow.events.get_by_id.return_value = sample_event
        mock_uow.tickets.get_by_event_and_section.return_value = sample_tickets

        use_case = ListTicketsUseCase(mock_uow)

        # When
        result = await use_case.list_tickets_by_section(
            event_id=event_id, section=section, subsection=subsection, seller_id=seller_id
        )

        # Then
        assert len(result) == 2
        assert result == sample_tickets
        mock_uow.events.get_by_id.assert_called_once_with(event_id=event_id)
        mock_uow.tickets.get_by_event_and_section.assert_called_once_with(
            event_id=event_id, section=section, subsection=subsection
        )

    @pytest.mark.asyncio
    async def test_seller_cannot_list_section_tickets_for_other_sellers_event(self, mock_uow):
        """Test that a seller cannot list section tickets for another seller's event."""
        # Given
        event_id = 1
        section = 'A'
        subsection = 1
        seller_id = 2  # Different seller
        other_seller_event = Mock(id=1, seller_id=1, name='Other Seller Event')
        mock_uow.events.get_by_id.return_value = other_seller_event

        use_case = ListTicketsUseCase(mock_uow)

        # When / Then
        with pytest.raises(ForbiddenError, match='Not authorized to view tickets for this event'):
            await use_case.list_tickets_by_section(
                event_id=event_id, section=section, subsection=subsection, seller_id=seller_id
            )
