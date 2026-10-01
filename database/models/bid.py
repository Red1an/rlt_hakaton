from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class BidModel(Base):
    __tablename__ = "bids"
    __table_args__ = (UniqueConstraint("lot_id", "supplier_inn"),)

    id: Mapped[int_pk]
    lot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("announcements.lot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_inn: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("suppliers.inn", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_winner: Mapped[bool] = mapped_column(Boolean, nullable=False)
