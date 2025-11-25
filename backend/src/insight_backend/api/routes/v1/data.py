from pathlib import Path

from fastapi import APIRouter, UploadFile, HTTPException, Depends, status
from sqlalchemy.orm import Session

from ....schemas.data import (
  IngestResponse,
  DataOverviewResponse,
  ExplorerColumnsConfigResponse,
  ExplorerTableConfig,
  UpdateExplorerColumnsRequest,
)
from ....schemas.tables import TableInfo, ColumnInfo
from ....services.data_service import DataService
from ....repositories.data_repository import DataRepository
from ....repositories.user_table_permission_repository import UserTablePermissionRepository
from ....repositories.explorer_column_repository import ExplorerColumnRepository
from ....core.config import settings
from ....core.database import get_session
from ....core.security import get_current_user, user_is_admin
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
  if not user_is_admin(current_user):
    allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
  return _service.list_tables(allowed_tables=allowed)


@router.get("/schema/{table_name}", response_model=list[ColumnInfo])
def get_table_schema(  # type: ignore[valid-type]
  table_name: str,
  current_user: User = Depends(get_current_user),
  session: Session = Depends(get_session),
) -> list[ColumnInfo]:
  allowed = None
  if not user_is_admin(current_user):
    allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
  try:
    return _service.get_schema(table_name, allowed_tables=allowed)
  except PermissionError as e:
    raise HTTPException(status_code=403, detail=str(e))
  except FileNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))


@router.get("/overview", response_model=DataOverviewResponse)
def get_data_overview(  # type: ignore[valid-type]
  current_user: User = Depends(get_current_user),
  session: Session = Depends(get_session),
) -> DataOverviewResponse:
  allowed = None
  if not user_is_admin(current_user):
    allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
  hidden_repo = ExplorerColumnRepository(session)
  hidden = hidden_repo.get_hidden_columns()
  return _service.get_overview(allowed_tables=allowed, hidden_columns=hidden)


@router.get("/overview/columns", response_model=ExplorerColumnsConfigResponse)
def get_explorer_columns_config(
  current_user: User = Depends(get_current_user),
  session: Session = Depends(get_session),
) -> ExplorerColumnsConfigResponse:
  if not user_is_admin(current_user):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

  tables_info = _service.list_tables()
  hidden_repo = ExplorerColumnRepository(session)
  hidden = hidden_repo.get_hidden_columns()

  tables_models: list[ExplorerTableConfig] = []
  for info in tables_info:
    schema = _service.get_schema(info.name)
    cols = [col.name for col in schema]
    hidden_set = {c.casefold() for c in hidden.get(info.name, set())}
    tables_models.append(
      ExplorerTableConfig(
        table=info.name,
        title=info.name,
        columns=[
          {
            "name": col,
            "label": col,
            "type": None,
            "hidden": col.casefold() in hidden_set,
          }
          for col in cols
        ],
      )
    )

  return ExplorerColumnsConfigResponse(tables=tables_models)


@router.put("/overview/columns/{table_name}", response_model=ExplorerTableConfig)
def update_explorer_columns_for_table(
  table_name: str,
  payload: UpdateExplorerColumnsRequest,
  current_user: User = Depends(get_current_user),
  session: Session = Depends(get_session),
) -> ExplorerTableConfig:
  if not user_is_admin(current_user):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

  # Ensure table exists
  available = {info.name for info in _service.list_tables()}
  if table_name not in available:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")

  # Filter hidden columns to those that exist in the schema
  schema = _service.get_schema(table_name)
  columns = [col.name for col in schema]
  columns_lookup = {c.casefold() for c in columns}
  filtered_hidden = [c for c in payload.hidden_columns if c.casefold() in columns_lookup]

  repo = ExplorerColumnRepository(session)
  normalized = repo.set_hidden_columns(table_name, filtered_hidden)

  hidden_set = {c.casefold() for c in normalized}
  return ExplorerTableConfig(
    table=table_name,
    title=table_name,
    columns=[
      {
        "name": col,
        "label": col,
        "type": None,
        "hidden": col.casefold() in hidden_set,
      }
      for col in columns
    ],
  )
