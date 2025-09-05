"""Product repository implementation."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.product.domain.product_entity import Product, ProductStatus
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
            seller_id=product.seller_id,
            is_active=product.is_active,
            status=product.status.value  # Convert enum to string
        )
        self.session.add(db_product)
        await self.session.flush()
        await self.session.refresh(db_product)  
        
        return Product(
            name=db_product.name,
            description=db_product.description,
            price=db_product.price, 
            seller_id=db_product.seller_id,
            is_active=db_product.is_active,
            status=ProductStatus(db_product.status),  # Convert string to enum
            id=db_product.id
        )
