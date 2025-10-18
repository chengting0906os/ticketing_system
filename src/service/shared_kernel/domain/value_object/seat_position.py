"""
Seat Position Value Object

座位位置值對象 - Shared Kernel
用於在 Ticketing 和 Seat Reservation 兩個 bounded context 之間共享座位位置概念
"""

from dataclasses import dataclass

from src.platform.exception.exceptions import DomainError


@dataclass
class SeatPosition:
    """座位位置（值對象）"""

    section: str
    subsection: int
    row: int
    seat: int

    @property
    def seat_id(self) -> str:
        """座位標識符"""
        return f'{self.section}-{self.subsection}-{self.row}-{self.seat}'

    @classmethod
    def from_seat_id(cls, seat_id: str) -> 'SeatPosition':
        """從座位ID創建座位位置"""
        try:
            parts = seat_id.split('-')
            return cls(
                section=parts[0], subsection=int(parts[1]), row=int(parts[2]), seat=int(parts[3])
            )
        except (ValueError, IndexError):
            raise DomainError(
                f'Invalid seat ID format: {seat_id}. Expected: section-subsection-row-seat', 400
            )
