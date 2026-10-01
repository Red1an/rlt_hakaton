from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class LotModel(Base):
    __tablename__ = "lots"

    id: Mapped[int_pk]
    lot_id: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(TEXT)
    okpd_code: Mapped[str] = mapped_column(
        TEXT,
        ForeignKey("okpd.code", ondelete="CASCADE"),
        nullable=False,
    )
