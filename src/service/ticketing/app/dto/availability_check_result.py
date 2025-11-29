"""Availability check result DTO."""

from typing import Optional

import attrs

from src.service.shared_kernel.domain.value_object import SubsectionConfig


@attrs.define(frozen=True)
class AvailabilityCheckResult:
    """
    Result of seat availability check with subsection config.

    This allows passing config (rows, seats_per_row, price) to downstream services,
    avoiding redundant Kvrocks lookups in Lua scripts.

    config is None when cache miss occurs (fail-open mode).
    """

    has_enough_seats: bool
    config: Optional[SubsectionConfig] = None
