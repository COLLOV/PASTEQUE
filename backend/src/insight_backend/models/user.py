from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

if TYPE_CHECKING:
    from .chart import Chart
    from .user_table_permission import UserTablePermission


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    charts: Mapped[list["Chart"]] = relationship("Chart", back_populates="user", cascade="all,delete-orphan")
    table_permissions: Mapped[list["UserTablePermission"]] = relationship(
        "UserTablePermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )
