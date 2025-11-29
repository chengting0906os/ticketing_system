"""
Seat Position Value Object

Seat Position Value Object - Shared Kernel
Used to share the seat position concept between Ticketing and Seat Reservation bounded contexts
"""

import attrs

from src.platform.exception.exceptions import DomainError


@attrs.define(frozen=True)
class SeatPosition:
    """Seat Position (Value Object)"""

    section: str
    subsection: int
    row: int
    seat: int

    @property
    def seat_id(self) -> str:
        """Seat identifier"""
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @classmethod
    def from_seat_id(cls, seat_id: str) -> 'SeatPosition':
        """Create seat position from seat ID"""
        try:
            parts = seat_id.split('-')
            return cls(
                section=parts[0], subsection=int(parts[1]), row=int(parts[2]), seat=int(parts[3])
            )
        except (ValueError, IndexError):
            raise DomainError(
                f'Invalid seat ID format: {seat_id}. Expected: section-subsection-row-seat', 400
            )
