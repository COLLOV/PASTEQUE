from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....core.security import get_current_user, user_is_admin
from ....models.user import User
from ....repositories.chart_repository import ChartRepository
from ....schemas.chart import ChartResponse, ChartSaveRequest
from ....services.chart_service import ChartService
from ....services.chart_assets import decode_chart_token


router = APIRouter(prefix="/charts")


@router.post("", response_model=ChartResponse, status_code=status.HTTP_201_CREATED)
def save_chart(  # type: ignore[valid-type]
    payload: ChartSaveRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartResponse:
    service = ChartService(ChartRepository(session))
    try:
        relative_path = decode_chart_token(payload.chart_path_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    chart = service.save_chart(
        user=current_user,
        prompt=payload.prompt,
        chart_path=relative_path,
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
    is_admin = user_is_admin(current_user)
    responses = [
        ChartResponse.from_model(
            chart,
            owner_username=chart.user.username if (is_admin and chart.user) else current_user.username,
        )
        for chart in charts
    ]
    return responses


@router.delete("/{chart_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chart(  # type: ignore[valid-type]
    chart_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    service = ChartService(ChartRepository(session))
    service.delete_chart(chart_id=chart_id, user=current_user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
