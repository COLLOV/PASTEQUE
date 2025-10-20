from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ....core.config import settings
from ....integrations.mindsdb_client import MindsDBClient
from ....services.mindsdb_sync import sync_all_tables


router = APIRouter(prefix="/mindsdb")


class SqlRequest(BaseModel):
    query: str


class SqlResponse(BaseModel):
    ok: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)


class SyncResponse(BaseModel):
    ok: bool = True
    uploaded: list[str] = Field(default_factory=list)


def _client() -> MindsDBClient:
    return MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)


@router.post("/sql", response_model=SqlResponse)
def run_sql(payload: SqlRequest) -> SqlResponse:  # type: ignore[valid-type]
    try:
        data = _client().sql(payload.query)
        return SqlResponse(ok=True, raw=data)
    except Exception as e:  # pragma: no cover - network/remote failure
        raise HTTPException(status_code=502, detail=f"MindsDB SQL failed: {e}")


@router.post("/sync-files", response_model=SyncResponse)
def sync_files_from_data() -> SyncResponse:  # type: ignore[valid-type]
    uploaded = sync_all_tables()
    return SyncResponse(ok=True, uploaded=uploaded)

