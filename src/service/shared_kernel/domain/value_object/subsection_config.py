"""Subsection configuration value object."""

import attrs


@attrs.define(frozen=True)
class SubsectionConfig:
    """
    Subsection configuration (Value Object).

    Contains the structural and pricing information for a subsection.
    This is shared across services to avoid redundant Kvrocks lookups.
    """

    rows: int
    cols: int
    price: int

    @property
    def total_seats(self) -> int:
        """Total number of seats in the subsection."""
        return self.rows * self.cols
