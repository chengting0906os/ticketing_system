"""Value Objects for Order Aggregate."""

import attrs


@attrs.define(frozen=True)
class ProductSnapshot:
    product_id: int
    name: str
    description: str
    price: int
    seller_id: int

    @classmethod
    def from_product(cls, product) -> 'ProductSnapshot':
        return cls(
            product_id=product.id or 0,
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id,
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
