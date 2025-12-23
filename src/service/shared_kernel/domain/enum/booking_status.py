"""Booking Status Enum"""

from enum import StrEnum


class BookingStatus(StrEnum):
    PROCESSING = 'processing'
    PENDING_PAYMENT = 'pending_payment'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    FAILED = 'failed'
