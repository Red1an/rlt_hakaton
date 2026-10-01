from sqlalchemy import Boolean, Float, ForeignKey, UniqueConstraint, Integer, String
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, int_pk
from .lot import LotModel


class AnnouncementModel(Base):
    __tablename__ = "announcements"
    __table_args__ = (UniqueConstraint("procedure_name", "lot_id", "customer_inn"),)

    id: Mapped[int_pk]
    procedure_name: Mapped[str] = mapped_column(TEXT)
    lot_id: Mapped[int] = mapped_column(Integer, ForeignKey("lots.id", ondelete="CASCADE"))
    start_price: Mapped[float] = mapped_column(Float)
    subject: Mapped[str] = mapped_column(TEXT)
    is_smp: Mapped[bool] = mapped_column(Boolean)
    customer_inn: Mapped[str] = mapped_column(String(12))
    customer_kpp: Mapped[str] = mapped_column(String(12))
    is_eshop_or_aisgz: Mapped[bool] = mapped_column(Boolean)

    lot: Mapped[LotModel] = relationship(lazy="selectin")
