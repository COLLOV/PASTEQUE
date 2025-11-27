from pathlib import Path

from fastapi import APIRouter, UploadFile, HTTPException, Depends, status
from sqlalchemy.orm import Session

from ....schemas.data import (
    IngestResponse,
    DataOverviewResponse,
    UpdateHiddenFieldsRequest,
    HiddenFieldsResponse,
    TableExplorePreview,
)
from ....schemas.tables import TableInfo, ColumnInfo
from ....services.data_service import DataService
from ....repositories.data_repository import DataRepository
from ....repositories.user_table_permission_repository import UserTablePermissionRepository
from ....repositories.data_source_preference_repository import DataSourcePreferenceRepository
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
    hidden_map = DataSourcePreferenceRepository(session).list_hidden_fields_by_source()
    include_hidden = user_is_admin(current_user)
    return _service.get_overview(
        allowed_tables=allowed,
        hidden_fields_by_source=hidden_map,
        include_hidden_fields=include_hidden,
    )


@router.put("/overview/{source}/hidden-fields", response_model=HiddenFieldsResponse)
def update_hidden_fields(  # type: ignore[valid-type]
    source: str,
    payload: UpdateHiddenFieldsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HiddenFieldsResponse:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    table_name = source.strip()
    if not table_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Table name is required")

    try:
        schema = _service.get_schema(table_name)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    available_fields = {col.name for col in schema}
    cleaned: list[str] = []
    seen: set[str] = set()
    unknown: list[str] = []
    for name in payload.hidden_fields:
        if not isinstance(name, str):
            continue
        trimmed = name.strip()
        if not trimmed:
            continue
        if trimmed not in available_fields:
            unknown.append(trimmed)
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(trimmed)

    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Colonnes inconnues pour {table_name}: {', '.join(sorted(set(unknown)))}",
        )

    repo = DataSourcePreferenceRepository(session)
    updated = repo.set_hidden_fields(source=table_name, hidden_fields=cleaned)
    session.commit()
    return HiddenFieldsResponse(source=table_name, hidden_fields=updated)


@router.get("/explore/{source}", response_model=TableExplorePreview)
def explore_table(  # type: ignore[valid-type]
    source: str,
    category: str,
    sub_category: str,
    limit: int = 25,
    offset: int = 0,
    sort_date: str | None = "desc",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TableExplorePreview:
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paramètre 'limit' invalide (doit être entre 1 et 500)",
        )
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paramètre 'offset' invalide (doit être >= 0)",
        )

    allowed = None
    if not user_is_admin(current_user):
        allowed = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)

    try:
        return _service.explore_table(
            table_name=source,
            category=category,
            sub_category=sub_category,
            limit=limit,
            offset=offset,
            sort_date=sort_date,
            allowed_tables=allowed,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
