from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ....core.config import settings
from ....integrations.mindsdb_client import MindsDBClient
from ....repositories.data_repository import DataRepository


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
    """Upload CSV/TSV files from settings.tables_dir to MindsDB `files` DB.

    Table name == filename stem. Idempotent on MindsDB side (last write wins).
    """
    repo = DataRepository(tables_dir=Path(settings.tables_dir))
    client = _client()
    uploaded: list[str] = []
    for p in repo._iter_table_files():  # reuse internal helper for now
        client.upload_file(p)
        uploaded.append(p.name)
    return SyncResponse(ok=True, uploaded=uploaded)

