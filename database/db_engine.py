import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from models import Base
from dotenv import load_dotenv
load_dotenv()


def _build_db_url():
    required = ["POSTGRES_SCHEME", "POSTGRES_HOST"]
    if any(not os.getenv(var) for var in required):
        raise ValueError(f"Missing required env vars: {required}")

    scheme = os.getenv("POSTGRES_SCHEME")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_NAME", "")

    return f"{scheme}://{user}:{password}@{host}:{port}/{name}"


class Database:
    _engine: AsyncEngine = None
    _sessionmaker: async_sessionmaker | None = None

    async def init(self):
        db_url = _build_db_url()
        self._engine = create_async_engine(
            db_url,
            echo=True,
            pool_pre_ping=True,
        )
        self._sessionmaker = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._sessionmaker:
            await self.init()

        if not self._sessionmaker:
            raise Exception("No sessionmaker")

        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_scalar(self, stmt):
        if not self._sessionmaker:
            await self.init()

        async with self._sessionmaker() as session:
            res = await session.execute(stmt)

        return res.scalar()

    async def get_all_scalars(self, stmt):
        if not self._sessionmaker:
            await self.init()

        async with self._sessionmaker() as session:
            res = (await session.execute(stmt)).scalars().all()

        return res


database = Database()