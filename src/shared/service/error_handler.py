"""Standardized error handling utilities for use cases."""

from typing import Any, Optional

from src.shared.exception.exceptions import DomainError, ForbiddenError, NotFoundError


class EntityNotFoundError:
    """Factory for entity not found errors."""

    @staticmethod
    def user(user_id: int) -> NotFoundError:
        """Create user not found error."""
        return NotFoundError(f'User with ID {user_id} not found')

    @staticmethod
    def event(event_id: int) -> NotFoundError:
        """Create event not found error."""
        return NotFoundError(f'Event with ID {event_id} not found')

    @staticmethod
    def booking(booking_id: int) -> NotFoundError:
        """Create booking not found error."""
        return NotFoundError(f'Booking with ID {booking_id} not found')

    @staticmethod
    def ticket(ticket_id: int) -> NotFoundError:
        """Create ticket not found error."""
        return NotFoundError(f'Ticket with ID {ticket_id} not found')

    @staticmethod
    def seat(seat_identifier: str) -> NotFoundError:
        """Create seat not found error."""
        return NotFoundError(f'Seat {seat_identifier} not found')


class BusinessRuleError:
    """Factory for business rule violation errors."""

    @staticmethod
    def ticket_not_available(
        ticket_id: Optional[int] = None, seat_identifier: Optional[str] = None
    ) -> DomainError:
        """Create ticket not available error."""
        identifier = f'ID {ticket_id}' if ticket_id else f'seat {seat_identifier}'
        return DomainError(f'Ticket {identifier} is not available', 400)

    @staticmethod
    def tickets_already_reserved() -> DomainError:
        """Create tickets already reserved error."""
        return DomainError('Tickets are already reserved', 400)

    @staticmethod
    def tickets_in_booking() -> DomainError:
        """Create tickets already in booking error."""
        return DomainError('Tickets are already in a booking', 400)

    @staticmethod
    def event_not_active() -> DomainError:
        """Create event not active error."""
        return DomainError('Event is not active', 400)

    @staticmethod
    def insufficient_tickets(requested: int, available: int) -> DomainError:
        """Create insufficient tickets error."""
        return DomainError(
            f'Not enough available tickets. Requested: {requested}, Available: {available}', 400
        )

    @staticmethod
    def mixed_events() -> DomainError:
        """Create mixed events error."""
        return DomainError('All tickets must be for the same event', 400)

    @staticmethod
    def booking_permission_denied() -> ForbiddenError:
        """Create booking permission denied error."""
        return ForbiddenError('Only the buyer can modify this booking')

    @staticmethod
    def cannot_cancel_paid_booking() -> DomainError:
        """Create cannot cancel paid booking error."""
        return DomainError('Cannot cancel paid booking', 400)

    @staticmethod
    def booking_already_cancelled() -> DomainError:
        """Create booking already cancelled error."""
        return DomainError('Booking already cancelled', 400)


class ValidationError:
    """Factory for validation errors."""

    @staticmethod
    def empty_selection(field_name: str) -> DomainError:
        """Create empty selection error."""
        return DomainError(f'{field_name} cannot be empty', 400)

    @staticmethod
    def conflicting_parameters(param1: str, param2: str) -> DomainError:
        """Create conflicting parameters error."""
        return DomainError(f'Cannot specify both {param1} and {param2}', 400)

    @staticmethod
    def missing_required_parameter(param_name: str, context: str) -> DomainError:
        """Create missing required parameter error."""
        return DomainError(f'{param_name} is required for {context}', 400)

    @staticmethod
    def mixed_approaches() -> DomainError:
        """Create mixed approaches error."""
        return DomainError('Cannot mix ticket_ids with seat selection mode', 400)

    @staticmethod
    def no_approach_specified() -> DomainError:
        """Create no approach specified error."""
        return DomainError('Must provide either ticket_ids or seat_selection_mode', 400)


def validate_entity_exists(entity: Any, error_factory_method) -> Any:
    """Validate that an entity exists, raise specific error if not."""
    if entity is None:
        raise error_factory_method()
    return entity


def validate_business_rule(condition: bool, error_factory_method) -> None:
    """Validate a business rule, raise specific error if violated."""
    if not condition:
        raise error_factory_method()
