from fastapi import APIRouter

from ....integrations.mcp_manager import MCPManager


router = APIRouter(prefix="/mcp")


@router.get("/servers")
def list_mcp_servers() -> list[dict]:  # type: ignore[valid-type]
    mgr = MCPManager()
    return [
        {"name": s.name, "command": s.command, "args": s.args, "env": list(s.env.keys())}
        for s in mgr.list_servers()
    ]
