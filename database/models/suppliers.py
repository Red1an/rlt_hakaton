from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class SuppliersModel(Base):
    __tablename__ = "suppliers"

    id: Mapped[int_pk]
    inn: Mapped[str] = mapped_column(String(12), unique=True)
    kpp: Mapped[str | None] = mapped_column(String(12), nullable=True)
    name: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    sum_price: Mapped[float] = mapped_column(Float, default=0)
    is_smp: Mapped[bool] = mapped_column(Boolean, default=False)
    okpds: Mapped[list[str]] = mapped_column(ARRAY(String(12)), default=list)
    source: Mapped[str] = mapped_column(String(20), default="dataset", server_default="dataset")
    site: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role_reason: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    contacts: Mapped[str | None] = mapped_column(TEXT, nullable=True)
