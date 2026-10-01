from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, int_pk
from .lot import LotModel


class AnnouncementModel(Base):
    __tablename__ = "announcements"

    id: Mapped[int_pk]
    procedure_name: Mapped[str] = mapped_column(TEXT)
    lot_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    publish_date: Mapped[date] = mapped_column(Date)
    start_price: Mapped[float] = mapped_column(Float)
    subject: Mapped[str] = mapped_column(TEXT)
    is_smp: Mapped[bool] = mapped_column(Boolean)
    customer_inn: Mapped[str] = mapped_column(String(12))
    customer_kpp: Mapped[str] = mapped_column(String(12))
    is_eshop_or_aisgz: Mapped[bool] = mapped_column(Boolean)

    products: Mapped[list[LotModel]] = relationship(lazy="selectin")
