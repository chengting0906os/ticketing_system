"""Value Objects for Order Aggregate."""

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
