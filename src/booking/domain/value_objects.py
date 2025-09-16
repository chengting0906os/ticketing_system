import attrs


@attrs.define(frozen=True)
class EventSnapshot:
    event_id: int
    name: str
    description: str
    price: int
    seller_id: int

    @classmethod
    def from_event(cls, event) -> 'EventSnapshot':
        return cls(
            event_id=event.id or 0,
            name=event.name,
            description=event.description,
            price=event.price,
            seller_id=event.seller_id,
        )


@attrs.define(frozen=True)
class BuyerInfo:
    buyer_id: int
    name: str
    email: str

    @classmethod
    def from_user(cls, user) -> 'BuyerInfo':
        return cls(buyer_id=user.id, name=user.name, email=user.email)


@attrs.define(frozen=True)
class SellerInfo:
    seller_id: int
    name: str
    email: str

    @classmethod
    def from_user(cls, user) -> 'SellerInfo':
        return cls(seller_id=user.id, name=user.name, email=user.email)


@attrs.define(frozen=True)
class TicketData:
    """Value Object for ticket data passed to booking aggregate"""

    id: int
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    seat_identifier: str

    @classmethod
    def from_ticket(cls, ticket) -> 'TicketData':
        return cls(
            id=ticket.id or 0,
            event_id=ticket.event_id,
            section=ticket.section,
            subsection=ticket.subsection,
            row=ticket.row,
            seat=ticket.seat,
            price=ticket.price,
            seat_identifier=ticket.seat_identifier,
        )


@attrs.define(frozen=True)
class TicketSnapshot:
    """Immutable snapshot for booking history"""

    ticket_id: int
    event_id: int
    section: str
    subsection: int
    row: int
    seat: int
    price: int
    seat_identifier: str

    @classmethod
    def from_ticket(cls, ticket) -> 'TicketSnapshot':
        return cls(
            ticket_id=ticket.id or 0,
            event_id=ticket.event_id,
            section=ticket.section,
            subsection=ticket.subsection,
            row=ticket.row,
            seat=ticket.seat,
            price=ticket.price,
            seat_identifier=ticket.seat_identifier,
        )

    @classmethod
    def from_ticket_data(cls, ticket_data: 'TicketData') -> 'TicketSnapshot':
        return cls(
            ticket_id=ticket_data.id,
            event_id=ticket_data.event_id,
            section=ticket_data.section,
            subsection=ticket_data.subsection,
            row=ticket_data.row,
            seat=ticket_data.seat,
            price=ticket_data.price,
            seat_identifier=ticket_data.seat_identifier,
        )
