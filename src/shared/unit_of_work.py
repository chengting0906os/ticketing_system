"""Unit of Work pattern implementation."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import get_async_session


if TYPE_CHECKING:
    from src.product.domain.product_repo import ProductRepo


class AbstractUnitOfWork(abc.ABC):
    products: ProductRepo

    async def __aenter__(self) -> AbstractUnitOfWork:
        return self

    async def __aexit__(self, *args):
        await self.rollback()

    async def commit(self):
        await self._commit()

    @abc.abstractmethod
    async def _commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    async def rollback(self):
        raise NotImplementedError


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def __aenter__(self):
        from src.product.infra.product_repo_impl import ProductRepoImpl
        self.products = ProductRepoImpl(self.session)
        return await super().__aenter__()
    
    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.session.close()
    
    async def _commit(self):
        await self.session.commit()
    
    async def rollback(self):
        await self.session.rollback()


def get_unit_of_work(session: AsyncSession = Depends(get_async_session)) -> AbstractUnitOfWork:
    return SqlAlchemyUnitOfWork(session)
