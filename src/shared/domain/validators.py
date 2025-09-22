"""Shared domain validation utilities."""

from typing import Any, Dict

from src.shared.config.business_config import BookingLimits, SeatIdentifierFormat
from src.shared.exception.exceptions import DomainError


class StringValidators:
    """Common string validation functions."""

    @staticmethod
    def validate_required_string(value: str, field_name: str) -> None:
        """Validate that a string is not empty or whitespace-only."""
        if not value or not value.strip():
            raise DomainError(f'{field_name} is required')

    @staticmethod
    def validate_name(_instance: Any, _attribute: Any, value: str) -> None:
        """Validate that a name field is not empty (for attrs validators)."""
        StringValidators.validate_required_string(value, 'Event name')

    @staticmethod
    def validate_description(_instance: Any, _attribute: Any, value: str) -> None:
        """Validate that a description field is not empty (for attrs validators)."""
        StringValidators.validate_required_string(value, 'Description')

    @staticmethod
    def validate_venue_name(_instance: Any, _attribute: Any, value: str) -> None:
        """Validate that a venue name field is not empty (for attrs validators)."""
        StringValidators.validate_required_string(value, 'Venue name')


class NumericValidators:
    """Common numeric validation functions."""

    @staticmethod
    def validate_positive_amount(value: int, field_name: str = 'Value') -> None:
        """Validate that a numeric value is positive."""
        if value < 0:
            raise DomainError(f'{field_name} must be over 0', 400)

    @staticmethod
    def validate_positive_price(_instance: Any, _attribute: Any, value: int) -> None:
        """Validate that a price is positive (for attrs validators)."""
        NumericValidators.validate_positive_amount(value, 'Price')


class StructuredDataValidators:
    """Validators for complex data structures."""

    @staticmethod
    def validate_seating_config(_instance: Any, _attribute: Any, value: Dict) -> None:
        """Validate that seating config is not empty (for attrs validators)."""
        if not value:
            raise DomainError('Seating config is required')

    @staticmethod
    def validate_non_empty_dict(value: Dict, field_name: str) -> None:
        """Validate that a dictionary is not empty."""
        if not value:
            raise DomainError(f'{field_name} is required')


class BusinessRuleValidators:
    """Validators for business-specific rules."""

    @staticmethod
    def validate_ticket_count(count: int) -> None:
        """Validate ticket count is within business limits."""
        if count < BookingLimits.MIN_TICKETS_PER_BOOKING:
            raise DomainError(
                f'Minimum {BookingLimits.MIN_TICKETS_PER_BOOKING} ticket required', 400
            )
        if count > BookingLimits.MAX_TICKETS_PER_BOOKING:
            raise DomainError(
                f'Maximum {BookingLimits.MAX_TICKETS_PER_BOOKING} tickets per booking', 400
            )

    @staticmethod
    def validate_seat_identifier_format(seat_identifier: str) -> tuple[str, int, int, int]:
        """Validate and parse seat identifier format (section-subsection-row-seat)."""
        parts = seat_identifier.split(SeatIdentifierFormat.SEPARATOR)
        if len(parts) != SeatIdentifierFormat.EXPECTED_PARTS:
            raise DomainError(
                f'Invalid seat format: {seat_identifier}. '
                f'Expected: {SeatIdentifierFormat.FORMAT_DESCRIPTION} (e.g., {SeatIdentifierFormat.EXAMPLE})',
                400,
            )

        section = parts[0]
        try:
            subsection = int(parts[1])
            row = int(parts[2])
            seat = int(parts[3])
        except ValueError:
            raise DomainError(
                f'Invalid seat format: {seat_identifier}. '
                f'Numbers expected for subsection, row, and seat in format: {SeatIdentifierFormat.FORMAT_DESCRIPTION}',
                400,
            )

        return section, subsection, row, seat
