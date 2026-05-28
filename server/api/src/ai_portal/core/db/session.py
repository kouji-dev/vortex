from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from ai_portal.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine for streaming endpoints.
# Prefer asyncpg on Windows because psycopg async refuses ProactorEventLoop.
# Fall back to psycopg async elsewhere (same URL works for both).
_async_db_url = settings.database_url
if _async_db_url.startswith("postgresql+psycopg://"):
    _async_db_url = _async_db_url.replace(
        "postgresql+psycopg://", "postgresql+asyncpg://", 1
    )
elif _async_db_url.startswith("postgresql://"):
    _async_db_url = _async_db_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )

async_engine = create_async_engine(_async_db_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def get_async_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an AsyncSession for streaming endpoints.

    Uses async_sessionmaker so the session manages its own transaction lifecycle,
    allowing rollback + new transaction in the streaming error path.
    """
    async with AsyncSessionLocal() as session:
        yield session
