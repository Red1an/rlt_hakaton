import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

load_dotenv()


def _build_db_url() -> str:
    required = ["POSTGRES_SCHEME", "POSTGRES_HOST"]
    if any(not os.getenv(var) for var in required):
        raise ValueError(f"Missing required env vars: {required}")

    scheme = os.getenv("POSTGRES_SCHEME")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DB", "")

    return f"{scheme}://{user}:{password}@{host}:{port}/{name}"


def _echo_enabled() -> bool:
    return os.getenv("SQL_ECHO", "").strip().lower() in {"1", "true", "yes", "on"}


class Database:
    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._sessionmaker: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self.init()
        return self._engine

    @property
    def sessionmaker(self) -> sessionmaker[Session]:
        if self._sessionmaker is None:
            self.init()
        return self._sessionmaker

    def init(self) -> None:
        with self._lock:
            if self._engine is not None:
                return
            self._engine = create_engine(
                _build_db_url(),
                echo=_echo_enabled(),
                pool_pre_ping=True,
            )
            self._sessionmaker = sessionmaker(self._engine, expire_on_commit=False)

        Base.metadata.create_all(self._engine)

    def dispose(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def get_scalar(self, stmt):
        with self.session() as session:
            return session.execute(stmt).scalar()

    def get_all_scalars(self, stmt):
        with self.session() as session:
            return session.execute(stmt).scalars().all()


database = Database()