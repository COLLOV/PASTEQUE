from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, joinedload

from ..models.chart import Chart


log = logging.getLogger("insight.repositories.chart")


class ChartRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        user_id: int,
        prompt: str,
        chart_url: str,
        tool_name: str | None,
        chart_title: str | None,
        chart_description: str | None,
        chart_spec: dict[str, Any] | None,
    ) -> Chart:
        chart = Chart(
            user_id=user_id,
            prompt=prompt,
            chart_url=chart_url,
            tool_name=tool_name,
            chart_title=chart_title,
            chart_description=chart_description,
            chart_spec=chart_spec,
        )
        self.session.add(chart)
        log.info("Chart queued for persistence (user_id=%s, url=%s)", user_id, chart_url)
        return chart

    def list_by_user(self, user_id: int) -> list[Chart]:
        charts = (
            self.session.query(Chart)
            .filter(Chart.user_id == user_id)
            .options(joinedload(Chart.user))
            .order_by(Chart.created_at.desc())
            .all()
        )
        log.info("Retrieved %d charts for user_id=%s", len(charts), user_id)
        return charts

    def list_all(self) -> list[Chart]:
        charts = (
            self.session.query(Chart)
            .options(joinedload(Chart.user))
            .order_by(Chart.created_at.desc())
            .all()
        )
        log.info("Retrieved %d charts (admin scope)", len(charts))
        return charts
