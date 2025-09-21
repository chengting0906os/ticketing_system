from unittest.mock import Mock

import pytest

from src.event_ticketing.use_case.list_tickets_use_case import ListTicketsUseCase
from src.shared.exception.exceptions import ForbiddenError, NotFoundError


class TestListTicketsUseCase:
    """Test cases for ListTicketsUseCase following TDD principles."""

    def _setup_use_case_with_event(self, mock_uow, sample_event):
        mock_uow.events.get_by_id.return_value = sample_event
        return ListTicketsUseCase(mock_uow)

    def _assert_event_call(self, mock_uow, event_id):
        mock_uow.events.get_by_id.assert_called_once_with(event_id=event_id)

    @pytest.mark.asyncio
    async def test_seller_can_list_all_tickets_for_their_event(
        self, mock_uow, sample_event, sample_tickets
    ):
        """Test that a seller can list all tickets (including sold ones) for their event."""
        # Given
        event_id = 1
        seller_id = 1
        use_case = self._setup_use_case_with_event(mock_uow, sample_event)
        mock_uow.tickets.get_by_event_id.return_value = sample_tickets

        # When
        result = await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

        # Then
        assert len(result) == 2
        assert result == sample_tickets
        self._assert_event_call(mock_uow, event_id)
        mock_uow.tickets.get_by_event_id.assert_called_once_with(event_id=event_id)

    @pytest.mark.asyncio
    async def test_buyer_can_only_list_available_tickets(
        self, mock_uow, sample_event, available_tickets
    ):
        """Test that a buyer (seller_id=None) can only see available tickets."""
        # Given
        event_id = 1
        seller_id = None
        use_case = self._setup_use_case_with_event(mock_uow, sample_event)
        mock_uow.tickets.get_available_tickets_by_event.return_value = available_tickets

        # When
        result = await use_case.list_tickets_by_event(event_id=event_id, seller_id=seller_id)

        # Then
        assert len(result) == 1
        assert result == available_tickets
        self._assert_event_call(mock_uow, event_id)
        mock_uow.tickets.get_available_tickets_by_event.assert_called_once_with(event_id=event_id)

    @pytest.mark.asyncio
    async def test_seller_cannot_list_tickets_for_other_sellers_event(self, mock_uow):
        """Test that a seller cannot list tickets for another seller's event."""
        # Given
        event_id = 1
        seller_id = 2
        other_seller_event = Mock(id=1, seller_id=1, name='Other Seller Event')
        use_case = self._setup_use_case_with_event(mock_uow, other_seller_event)

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
    async def test_seller_can_list_tickets_by_event_ticket_subsection(
        self, mock_uow, sample_event, sample_tickets
    ):
        """Test that a seller can list tickets for specific section of their event."""
        # Given
        event_id = 1
        section = 'A'
        subsection = 1
        seller_id = 1
        use_case = self._setup_use_case_with_event(mock_uow, sample_event)
        mock_uow.tickets.list_by_event_section_and_subsection.return_value = sample_tickets

        # When
        result = await use_case.list_tickets_by_section(
            event_id=event_id, section=section, subsection=subsection, seller_id=seller_id
        )

        # Then
        assert len(result) == 2
        assert result == sample_tickets
        self._assert_event_call(mock_uow, event_id)
        mock_uow.tickets.list_by_event_section_and_subsection.assert_called_once_with(
            event_id=event_id, section=section, subsection=subsection
        )

    @pytest.mark.asyncio
    async def test_seller_cannot_list_section_tickets_for_other_sellers_event(self, mock_uow):
        """Test that a seller cannot list section tickets for another seller's event."""
        # Given
        event_id = 1
        section = 'A'
        subsection = 1
        seller_id = 2
        other_seller_event = Mock(id=1, seller_id=1, name='Other Seller Event')
        use_case = self._setup_use_case_with_event(mock_uow, other_seller_event)

        # When / Then
        with pytest.raises(ForbiddenError, match='Not authorized to view tickets for this event'):
            await use_case.list_tickets_by_section(
                event_id=event_id, section=section, subsection=subsection, seller_id=seller_id
            )
