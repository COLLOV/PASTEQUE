from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ....integrations.neo4j_client import Neo4jClientError
from ....services.neo4j_ingest import Neo4jIngestionError, Neo4jIngestionService


router = APIRouter(prefix="/neo4j")


class SyncResponse(BaseModel):
    ok: bool = True
    datasets: dict[str, int] = Field(default_factory=dict)


@router.post("/sync", response_model=SyncResponse)
def sync_neo4j() -> SyncResponse:  # type: ignore[valid-type]
    service = Neo4jIngestionService()
    try:
        summary = service.sync_all()
    except (Neo4jIngestionError, Neo4jClientError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return SyncResponse(ok=True, datasets=summary)
