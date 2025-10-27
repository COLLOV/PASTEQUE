from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ....integrations.mcp_manager import MCPManager
from ....schemas.mcp_chart import ChartRequest, ChartResponse
from ....services.chart_assets import decode_chart_token, to_absolute_path
from ....services.mcp_chart_service import ChartGenerationError, ChartGenerationService


router = APIRouter(prefix="/mcp")


@router.get("/servers")
def list_mcp_servers() -> list[dict]:  # type: ignore[valid-type]
    mgr = MCPManager()
    return [
        {"name": s.name, "command": s.command, "args": s.args, "env": list(s.env.keys())}
        for s in mgr.list_servers()
    ]


@router.post("/chart", response_model=ChartResponse)
async def generate_mcp_chart(payload: ChartRequest) -> ChartResponse:  # type: ignore[valid-type]
    service = ChartGenerationService()
    try:
        result = await service.generate_chart(
            prompt=payload.prompt,
            dataset=payload.dataset,
            answer=payload.answer,
        )
    except ChartGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ChartResponse(
        prompt=result.prompt,
        chart_url=result.chart_url,
        chart_path_token=result.chart_path_token,
        chart_preview_data_uri=result.chart_preview_data_uri,
        tool_name=result.tool_name,
        chart_title=result.chart_title,
        chart_description=result.chart_description,
        chart_spec=result.chart_spec,
        source_sql=result.source_sql,
        source_row_count=result.source_row_count,
    )


@router.get("/chart/image/{token}")
def get_chart_image(token: str) -> FileResponse:  # type: ignore[valid-type]
    try:
        relative_path = decode_chart_token(token)
        absolute_path = to_absolute_path(relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not absolute_path.exists():
        raise HTTPException(status_code=404, detail="Image de graphique introuvable")

    return FileResponse(str(absolute_path))
