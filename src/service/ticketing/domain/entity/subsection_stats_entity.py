import attrs


@attrs.define
class SubsectionStatsEntity:
    """Subsection-level statistics entity for seat availability tracking."""

    event_id: int
    section: str
    subsection: int
    price: int
    available: int
    reserved: int
    sold: int
    updated_at: int

    @property
    def total(self) -> int:
        return self.available + self.reserved + self.sold
