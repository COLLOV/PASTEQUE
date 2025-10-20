from fastapi import APIRouter, HTTPException

from ....integrations.mcp_manager import MCPManager
from ....schemas.mcp_chart import ChartRequest, ChartResponse
from ....services.mcp_chart_service import ChartGenerationError, ChartGenerationService


router = APIRouter(prefix="/mcp")


@router.get("/servers")
def list_mcp_servers() -> list[dict]:  # type: ignore[valid-type]
    mgr = MCPManager()
    return [
        {"name": s.name, "command": s.command, "args": s.args, "env": list(s.env.keys())}
        for s in mgr.list_servers()
    ]


@router.post("/charts", response_model=ChartResponse)
def generate_chart(payload: ChartRequest) -> ChartResponse:  # type: ignore[valid-type]
    service = ChartGenerationService()
    try:
        result = service.generate(tool=payload.tool, arguments=payload.arguments)
    except ChartGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ChartResponse(**result)
