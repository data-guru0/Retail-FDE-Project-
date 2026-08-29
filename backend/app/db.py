"""Async SQLAlchemy engine + session dependency."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import get_settings

_engine = create_async_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10)
Session = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with Session() as s:
        yield s


def engine():
    return _engine
