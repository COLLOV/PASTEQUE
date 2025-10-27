from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from ..models.chart import Chart
from ..models.user import User
from ..repositories.chart_repository import ChartRepository
from ..core.security import user_is_admin


log = logging.getLogger("insight.services.chart")


class ChartService:
    def __init__(self, repo: ChartRepository):
        self.repo = repo

    def save_chart(
        self,
        *,
        user: User,
        prompt: str,
        chart_path: str,
        tool_name: str | None,
        chart_title: str | None,
        chart_description: str | None,
        chart_spec: dict[str, Any] | None,
    ) -> Chart:
        chart = self.repo.create(
            user_id=user.id,
            prompt=prompt,
            chart_path=chart_path,
            tool_name=tool_name,
            chart_title=chart_title,
            chart_description=chart_description,
            chart_spec=chart_spec,
        )
        log.info("Chart saved request by user=%s path=%s", user.username, chart_path)
        # Attach relationship for immediate serialization without extra round-trip.
        chart.user = user
        return chart

    def list_charts(self, user: User) -> list[Chart]:
        if user_is_admin(user):
            charts = self.repo.list_all()
        else:
            charts = self.repo.list_by_user(user.id)
        log.debug("Chart listing for user=%s count=%d", user.username, len(charts))
        return charts

    def delete_chart(self, *, chart_id: int, user: User) -> None:
        chart = self.repo.get_by_id(chart_id)
        if not chart:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chart not found")

        is_admin = user_is_admin(user)
        if not is_admin and chart.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete chart")

        owner = chart.user.username if chart.user else "unknown"
        self.repo.delete(chart)
        log.info("Chart deletion requested by user=%s chart_id=%s owner=%s", user.username, chart_id, owner)
