from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....core.security import get_current_user
from ....core.config import settings
from ....models.user import User
from ....repositories.chart_repository import ChartRepository
from ....schemas.chart import ChartResponse, ChartSaveRequest
from ....services.chart_service import ChartService


router = APIRouter(prefix="/charts")


@router.post("", response_model=ChartResponse, status_code=status.HTTP_201_CREATED)
def save_chart(  # type: ignore[valid-type]
    payload: ChartSaveRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartResponse:
    service = ChartService(ChartRepository(session))
    chart = service.save_chart(
        user=current_user,
        prompt=payload.prompt,
        chart_url=payload.chart_url,
        tool_name=payload.tool_name,
        chart_title=payload.chart_title,
        chart_description=payload.chart_description,
        chart_spec=payload.chart_spec,
    )
    session.commit()
    session.refresh(chart)
    return ChartResponse.from_model(chart, owner_username=current_user.username)


@router.get("", response_model=list[ChartResponse])
def list_charts(  # type: ignore[valid-type]
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ChartResponse]:
    service = ChartService(ChartRepository(session))
    charts = service.list_charts(current_user)
    is_admin = current_user.username == settings.admin_username
    responses = [
        ChartResponse.from_model(
            chart,
            owner_username=chart.user.username if (is_admin and chart.user) else current_user.username,
        )
        for chart in charts
    ]
    return responses
