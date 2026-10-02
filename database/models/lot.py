from sqlalchemy import ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class LotModel(Base):
    __tablename__ = "lots"

    id: Mapped[int_pk]
    lot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("announcements.lot_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_name: Mapped[str] = mapped_column(TEXT)
    okpd_code: Mapped[str | None] = mapped_column(
        TEXT,
        ForeignKey("okpd.code", ondelete="CASCADE"),
        nullable=True,
    )


Index("ix_lots_okpd_group", func.left(LotModel.okpd_code, 5), LotModel.lot_id)
