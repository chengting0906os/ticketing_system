"""Product repository implementation."""

from typing import List, Optional

from sqlalchemy import delete as sql_delete, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.product.domain.product_entity import Product, ProductStatus
from src.product.domain.product_repo import ProductRepo
from src.product.infra.product_model import ProductModel
from src.shared.exception.exceptions import DomainError
from src.shared.logging.loguru_io import Logger


class ProductRepoImpl(ProductRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(db_product: ProductModel) -> Product:
        """Convert database model to domain entity."""
        return Product(
            name=db_product.name,
            description=db_product.description,
            price=db_product.price,
            seller_id=db_product.seller_id,
            is_active=db_product.is_active,
            status=ProductStatus(db_product.status),
            id=db_product.id,
        )

    @Logger.io
    async def create(self, product: Product) -> Product:
        db_product = ProductModel(
            name=product.name,
            description=product.description,
            price=product.price,
            seller_id=product.seller_id,
            is_active=product.is_active,
            status=product.status.value,  # Convert enum to string
        )
        self.session.add(db_product)
        await self.session.flush()
        await self.session.refresh(db_product)

        return ProductRepoImpl._to_entity(db_product)

    @Logger.io
    async def get_by_id(self, product_id: int) -> Optional[Product]:
        result = await self.session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        db_product = result.scalar_one_or_none()

        if not db_product:
            return None

        return ProductRepoImpl._to_entity(db_product)

    @Logger.io
    async def update(self, product: Product) -> Product:
        stmt = (
            sql_update(ProductModel)
            .where(ProductModel.id == product.id)
            .values(
                name=product.name,
                description=product.description,
                price=product.price,
                is_active=product.is_active,
                status=product.status.value,
            )
            .returning(ProductModel)
        )

        result = await self.session.execute(stmt)
        db_product = result.scalar_one_or_none()

        if not db_product:
            raise ValueError(f'Product with id {product.id} not found')

        return ProductRepoImpl._to_entity(db_product)

    @Logger.io
    async def delete(self, product_id: int) -> bool:
        stmt = (
            sql_delete(ProductModel).where(ProductModel.id == product_id).returning(ProductModel.id)
        )

        result = await self.session.execute(stmt)
        deleted_id = result.scalar_one_or_none()

        return deleted_id is not None

    @Logger.io
    async def get_by_seller(self, seller_id: int) -> List[Product]:
        result = await self.session.execute(
            select(ProductModel)
            .where(ProductModel.seller_id == seller_id)
            .order_by(ProductModel.id)
        )
        db_products = result.scalars().all()

        return [ProductRepoImpl._to_entity(db_product) for db_product in db_products]

    async def list_available(self) -> List[Product]:
        result = await self.session.execute(
            select(ProductModel)
            .where(ProductModel.is_active)
            .where(ProductModel.status == ProductStatus.AVAILABLE.value)
            .order_by(ProductModel.id)
        )
        db_products = result.scalars().all()

        return [ProductRepoImpl._to_entity(db_product) for db_product in db_products]

    @Logger.io
    async def release_product_atomically(self, product_id: int) -> Product:
        stmt = (
            sql_update(ProductModel)
            .where(ProductModel.id == product_id)
            .where(ProductModel.status == ProductStatus.RESERVED.value)
            .values(status=ProductStatus.AVAILABLE.value)
            .returning(ProductModel)
        )

        result = await self.session.execute(stmt)
        db_product = result.scalar_one_or_none()

        if not db_product:
            raise DomainError('Unable to release product')

        return ProductRepoImpl._to_entity(db_product)
