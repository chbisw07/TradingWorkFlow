"""One global, versioned, provider-derived F&O liquidity cache."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from twf.infrastructure.database import Base


class FnoLiquidityRow(Base):
    __tablename__ = "fno_liquidity_cache"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
