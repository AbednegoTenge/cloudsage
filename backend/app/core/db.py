"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Environment, Settings, get_settings


@lru_cache
def _engine(url: str, echo: bool, pool_size: int, pooled: bool) -> AsyncEngine:
    if not pooled:
        # Tests run each client on its own event loop; pooled connections can't cross loops.
        return create_async_engine(url, echo=echo, poolclass=NullPool)
    return create_async_engine(url, echo=echo, pool_size=pool_size, pool_pre_ping=True)


def get_engine(settings: Settings) -> AsyncEngine:
    return _engine(
        settings.database_url,
        settings.database_echo,
        settings.database_pool_size,
        settings.environment is not Environment.TEST,
    )


@lru_cache
def _sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def get_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    return _sessionmaker(get_engine(settings))


async def get_db(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with get_sessionmaker(settings)() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
