from fastapi import APIRouter, UploadFile, HTTPException
from ....schemas.data import IngestResponse
from ....schemas.tables import TableInfo, ColumnInfo
from ....services.data_service import DataService
from ....repositories.data_repository import DataRepository
from ....core.config import settings
from pathlib import Path

router = APIRouter(prefix="/data")
_service = DataService(repo=DataRepository(tables_dir=Path(settings.tables_dir)))


@router.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile) -> IngestResponse:  # type: ignore[valid-type]
    """Endpoint placeholder d’ingestion de données.
    Délègue à DataService (non implémenté).
    """
    raise NotImplementedError("Data ingestion not implemented yet")


@router.get("/tables", response_model=list[TableInfo])
def list_tables() -> list[TableInfo]:  # type: ignore[valid-type]
    return _service.list_tables()


@router.get("/schema/{table_name}", response_model=list[ColumnInfo])
def get_table_schema(table_name: str) -> list[ColumnInfo]:  # type: ignore[valid-type]
    try:
        return _service.get_schema(table_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
