from fastapi import APIRouter, HTTPException

from ....integrations.mcp_manager import MCPManager
from ....schemas.mcp_chart import ChartCollectionResponse
from ....services.mcp_chart_service import ChartGenerationError, ChartGenerationService


router = APIRouter(prefix="/mcp")


@router.get("/servers")
def list_mcp_servers() -> list[dict]:  # type: ignore[valid-type]
    mgr = MCPManager()
    return [
        {"name": s.name, "command": s.command, "args": s.args, "env": list(s.env.keys())}
        for s in mgr.list_servers()
    ]


@router.get("/charts", response_model=ChartCollectionResponse)
def generate_mcp_charts() -> ChartCollectionResponse:  # type: ignore[valid-type]
    service = ChartGenerationService()
    try:
        charts = service.generate()
    except ChartGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return ChartCollectionResponse(
        charts=charts,
        metadata={
            "provider": "mcp-server-chart",
            "count": len(charts),
        },
    )
