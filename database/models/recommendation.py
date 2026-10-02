from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LotRecommendationModel(Base):
    __tablename__ = "lot_recommendations"

    lot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("announcements.lot_id", ondelete="CASCADE"),
        primary_key=True,
    )
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
