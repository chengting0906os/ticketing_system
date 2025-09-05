"""Product repository implementation."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.product.domain.product_entity import Product
from src.product.domain.product_repo import ProductRepo
from src.product.infra.product_model import ProductModel


class ProductRepoImpl(ProductRepo):
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, product: Product) -> Product:
        db_product = ProductModel(
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id
        )
        self.session.add(db_product)
        await self.session.flush()
        await self.session.refresh(db_product)  # 把 DB 裡的 id 同步回來
        
        return Product(
            name=db_product.name,
            description=db_product.description,
            price=int(db_product.price),  # Convert to int from DB
            seller_id=db_product.seller_id,
            id=db_product.id
        )
