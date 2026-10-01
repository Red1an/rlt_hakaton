from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, int_pk


class OKPDModel(Base):
    __tablename__ = "okpd"

    id: Mapped[int_pk]
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
