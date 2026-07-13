"""
app/database.py
----------------
Async SQLAlchemy engine + session factory. Works with either PostgreSQL
(asyncpg, for production) or SQLite (aiosqlite, for local dev/tests) purely
based on DATABASE_URL — no code changes needed between environments.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_models():
    """Creates tables if they don't exist. For serious production use, swap this
    for Alembic migrations — kept simple here for fast, reliable first deploys."""
    import app.models  # noqa: F401  (ensure models are registered on Base.metadata)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
