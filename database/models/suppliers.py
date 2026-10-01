from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class SuppliersModel(Base):
    __tablename__ = "suppliers"
    __table_args__ = ("inn", "kpp", "name")

    id: Mapped[int_pk]
    inn: Mapped[str] = mapped_column(String(12), unique=True)
    kpp: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sum_price: Mapped[float] = mapped_column(Float, default=0)
    is_smp: Mapped[bool] = mapped_column(Boolean, default=False)
    okpds: Mapped[list[str]] = mapped_column(ARRAY(String(12)), default=list)
