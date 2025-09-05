from src.order.domain.order_entity import Order, OrderStatus
from src.order.domain.order_repo import OrderRepo
from src.product.domain.product_entity import ProductStatus
from src.product.domain.product_repo import ProductRepo
from src.shared.exceptions import DomainException
from src.shared.uow import UnitOfWork
from src.user.domain.user_entity import UserRole
from src.user.domain.user_repo import UserRepo


class CreateOrderRequest(UseCase.Request):
    buyer_id: int
    product_id: int


class CreateOrderResponse(UseCase.Response):
    id: int
    buyer_id: int
    seller_id: int
    product_id: int
    price: int
    status: str


class CreateOrderUseCase(UseCase):
    def __init__(
        self,
        uow: UnitOfWork,
        order_repo: OrderRepo,
        product_repo: ProductRepo,
        user_repo: UserRepo,
    ) -> None:
        self.uow = uow
        self.order_repo = order_repo
        self.product_repo = product_repo
        self.user_repo = user_repo

    async def execute(self, request: CreateOrderRequest) -> CreateOrderResponse:
        async with self.uow:
            buyer = await self.user_repo.get_by_id(request.buyer_id)
            
            if not buyer:
                raise DomainException(status_code=404, message="Buyer not found")
            
            if buyer.role != UserRole.BUYER.value:
                raise DomainException(status_code=403, message="Only buyers can create orders")
            
            product = await self.product_repo.get_by_id(request.product_id)
            if not product:
                raise DomainException(status_code=404, message="Product not found")
            
            if not product.is_active:
                raise DomainException(status_code=400, message="Product not active")
            
            if product.status != ProductStatus.AVAILABLE:
                raise DomainException(status_code=400, message="Product not available")
            
            if product.id:
                existing_order = await self.order_repo.get_by_product_id(product.id)
                if existing_order:
                    raise DomainException(status_code=400, message="Product already has an active order")
            
            order = Order(
                buyer_id=request.buyer_id,
                seller_id=product.seller_id,
                product_id=product.id or 0,  # This should never be 0 as product must exist
                price=product.price,
                status=OrderStatus.PENDING_PAYMENT,
            )
            
            created_order = await self.order_repo.create(order)
            
            product.status = ProductStatus.RESERVED
            await self.product_repo.update(product)
            
            await self.uow.commit()
            
            return CreateOrderResponse(
                id=created_order.id,
                buyer_id=created_order.buyer_id,
                seller_id=created_order.seller_id,
                product_id=created_order.product_id,
                price=created_order.price,
                status=created_order.status.value,
            )
