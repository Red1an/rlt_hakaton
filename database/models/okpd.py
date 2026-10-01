from sqlalchemy import String
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class OKPDModel(Base):
    __tablename__ = "okpd"

    id: Mapped[int_pk]
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(TEXT, nullable=True)
