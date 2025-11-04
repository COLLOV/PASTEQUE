from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..core.config import settings
from ..models.chart import Chart
from ..models.conversation import Conversation, ConversationMessage
from ..models.user import User


log = logging.getLogger("insight.repositories.user")


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> User | None:
        return (
            self.session.query(User)
            .filter(User.username == username)
            .one_or_none()
        )

    def create_user(
        self,
        username: str,
        password_hash: str,
        *,
        is_active: bool = True,
        is_admin: bool = False,
        must_reset_password: bool = True,
    ) -> User:
        if is_admin and username != settings.admin_username:
            raise ValueError("Admin flag reserved for configured admin username")
        user = User(
            username=username,
            password_hash=password_hash,
            is_active=is_active,
            is_admin=is_admin,
            must_reset_password=must_reset_password,
        )
        self.session.add(user)
        self.session.flush()
        log.info(
            "User created: %s (admin=%s, must_reset_password=%s)",
            username,
            is_admin,
            must_reset_password,
        )
        return user

    def list_all(self) -> list[User]:
        users = (
            self.session.query(User)
            .options(selectinload(User.table_permissions))
            .order_by(User.username.asc())
            .all()
        )
        log.debug("Loaded %d users (admin scope)", len(users))
        return users

    def delete_user(self, user: User) -> None:
        self.session.delete(user)
        log.info("User deleted: %s", user.username)

    # ----- Settings helpers -----
    def get_settings(self, *, user_id: int) -> dict[str, Any]:
        user = self.session.query(User).filter(User.id == user_id).one_or_none()
        return dict(user.settings or {}) if user else {}

    def set_settings(self, *, user_id: int, settings: dict[str, Any]) -> dict[str, Any]:
        payload = dict(settings or {})
        self.session.query(User).filter(User.id == user_id).update({User.settings: payload})
        log.info("User settings updated (user_id=%s, keys=%s)", user_id, ",".join(sorted(payload.keys())))
        return payload

    def get_default_excluded_tables(self, *, user_id: int) -> list[str]:
        s = self.get_settings(user_id=user_id)
        raw = s.get("default_exclude_tables") if isinstance(s, dict) else None
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                key = item.strip()
                if key.casefold() in seen:
                    continue
                seen.add(key.casefold())
                out.append(key)
        return out

    def set_default_excluded_tables(self, *, user_id: int, tables: list[str]) -> list[str]:
        from ..utils.validation import normalize_table_names
        normalized = normalize_table_names(tables)
        s = self.get_settings(user_id=user_id)
        s["default_exclude_tables"] = normalized
        self.set_settings(user_id=user_id, settings=s)
        return normalized

    # ----- Admin analytics -----
    def gather_usage_stats(self) -> dict[str, Any]:
        """Aggregate usage metrics for admin dashboard."""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        bind = self.session.get_bind()
        if bind is not None and bind.dialect.name == "sqlite":
            week_ago_filter = week_ago.replace(tzinfo=None)
        else:
            week_ago_filter = week_ago

        total_users = int(self.session.query(func.count(User.id)).scalar() or 0)
        total_conversations = int(self.session.query(func.count(Conversation.id)).scalar() or 0)
        total_messages = int(self.session.query(func.count(ConversationMessage.id)).scalar() or 0)
        total_charts = int(self.session.query(func.count(Chart.id)).scalar() or 0)

        conversations_last_7_days = int(
            self.session.query(func.count(Conversation.id))
            .filter(Conversation.created_at >= week_ago_filter)
            .scalar()
            or 0
        )
        messages_last_7_days = int(
            self.session.query(func.count(ConversationMessage.id))
            .filter(ConversationMessage.created_at >= week_ago_filter)
            .scalar()
            or 0
        )
        charts_last_7_days = int(
            self.session.query(func.count(Chart.id))
            .filter(Chart.created_at >= week_ago_filter)
            .scalar()
            or 0
        )

        conv_stats = (
            self.session.query(
                Conversation.user_id.label("user_id"),
                func.count(Conversation.id).label("conversation_count"),
                func.max(Conversation.updated_at).label("conversation_last_activity"),
            )
            .group_by(Conversation.user_id)
            .subquery()
        )

        message_stats = (
            self.session.query(
                Conversation.user_id.label("user_id"),
                func.count(ConversationMessage.id).label("message_count"),
                func.max(ConversationMessage.created_at).label("message_last_activity"),
            )
            .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
            .group_by(Conversation.user_id)
            .subquery()
        )

        chart_stats = (
            self.session.query(
                Chart.user_id.label("user_id"),
                func.count(Chart.id).label("chart_count"),
                func.max(Chart.created_at).label("chart_last_activity"),
            )
            .group_by(Chart.user_id)
            .subquery()
        )

        rows = (
            self.session.query(
                User.username,
                User.is_active,
                User.created_at,
                func.coalesce(conv_stats.c.conversation_count, 0).label("conversation_count"),
                func.coalesce(message_stats.c.message_count, 0).label("message_count"),
                func.coalesce(chart_stats.c.chart_count, 0).label("chart_count"),
                conv_stats.c.conversation_last_activity,
                message_stats.c.message_last_activity,
                chart_stats.c.chart_last_activity,
            )
            .outerjoin(conv_stats, conv_stats.c.user_id == User.id)
            .outerjoin(message_stats, message_stats.c.user_id == User.id)
            .outerjoin(chart_stats, chart_stats.c.user_id == User.id)
            .order_by(User.username.asc())
            .all()
        )

        per_user: list[dict[str, Any]] = []
        active_users_last_7_days = 0

        def normalize(value: Any) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError:
                    return None
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            return None

        for row in rows:
            conversation_last = normalize(row.conversation_last_activity)
            message_last = normalize(row.message_last_activity)
            chart_last = normalize(row.chart_last_activity)
            last_candidates = [candidate for candidate in (conversation_last, message_last, chart_last) if candidate]
            last_activity = max(last_candidates, default=None)
            if last_activity and last_activity >= week_ago:
                active_users_last_7_days += 1
            created_at = normalize(row.created_at) or now
            per_user.append(
                {
                    "username": row.username,
                    "is_active": bool(row.is_active),
                    "created_at": created_at,
                    "conversations": int(row.conversation_count or 0),
                    "messages": int(row.message_count or 0),
                    "charts": int(row.chart_count or 0),
                    "last_activity_at": last_activity,
                }
            )

        totals = {
            "users": total_users,
            "conversations": total_conversations,
            "messages": total_messages,
            "charts": total_charts,
            "conversations_last_7_days": conversations_last_7_days,
            "messages_last_7_days": messages_last_7_days,
            "charts_last_7_days": charts_last_7_days,
            "active_users_last_7_days": active_users_last_7_days,
        }
        log.info(
            "Usage stats computed (users=%s, conversations=%s, messages=%s, charts=%s)",
            totals["users"],
            totals["conversations"],
            totals["messages"],
            totals["charts"],
        )
        return {
            "generated_at": now,
            "totals": totals,
            "per_user": per_user,
        }
