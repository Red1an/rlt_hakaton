from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
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
    ogrn: Mapped[str | None] = mapped_column(String(15), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reg_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    okved_main: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address: Mapped[str | None] = mapped_column(TEXT, nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    opf: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_individual: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
