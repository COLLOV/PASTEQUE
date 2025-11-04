from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User

from ..core.database import Base


class Chart(Base):
    __tablename__ = "charts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    chart_url: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chart_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    chart_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="charts")

