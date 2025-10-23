from pathlib import Path

from fastapi import APIRouter, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session

from ....schemas.data import IngestResponse
from ....schemas.tables import TableInfo, ColumnInfo
from ....services.data_service import DataService
from ....repositories.data_repository import DataRepository
from ....repositories.user_table_permission_repository import UserTablePermissionRepository
from ....core.config import settings
from ....core.database import get_session
from ....core.security import get_current_user
from ....models.user import User

router = APIRouter(prefix="/data")
_service = DataService(repo=DataRepository(tables_dir=Path(settings.tables_dir)))


@router.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile) -> IngestResponse:  # type: ignore[valid-type]
    """Endpoint placeholder d’ingestion de données.
    Délègue à DataService (non implémenté).
    """
    raise NotImplementedError("Data ingestion not implemented yet")


@router.get("/tables", response_model=list[TableInfo])
def list_tables(  # type: ignore[valid-type]
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[TableInfo]:
    allowed = None
    if current_user.username != settings.admin_username:
        allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
    return _service.list_tables(allowed_tables=allowed)


@router.get("/schema/{table_name}", response_model=list[ColumnInfo])
def get_table_schema(  # type: ignore[valid-type]
    table_name: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ColumnInfo]:
    allowed = None
    if current_user.username != settings.admin_username:
        allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
    try:
        return _service.get_schema(table_name, allowed_tables=allowed)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
