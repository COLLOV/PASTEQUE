from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class ExplorerHiddenColumn(Base):
    __tablename__ = "explorer_hidden_columns"
    __table_args__ = (
        UniqueConstraint(
            "table_name",
            "column_name",
            name="uq_explorer_hidden_columns_table_column",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

