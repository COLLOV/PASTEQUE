from fastapi import APIRouter, HTTPException, Depends, Response

from ....schemas.dictionary import DictionaryTable, DictionaryTableSummary
from ....services.dictionary_service import DictionaryService
from ....repositories.data_repository import DataRepository
from ....repositories.dictionary_repository import DataDictionaryRepository
from ....core.config import settings
from ....core.security import get_current_user, user_is_admin
from ....models.user import User

router = APIRouter(prefix="/dictionary")
_service = DictionaryService(
    data_repo=DataRepository(tables_dir=settings.tables_dir),
    dictionary_repo=DataDictionaryRepository(directory=settings.data_dictionary_dir),
)


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not user_is_admin(current_user):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs.")
    return current_user


@router.get("", response_model=list[DictionaryTableSummary])
def list_dictionaries(  # type: ignore[valid-type]
    current_user: User = Depends(_require_admin),
) -> list[DictionaryTableSummary]:
    return _service.list_tables()


@router.get("/{table_name}", response_model=DictionaryTable)
def get_dictionary(  # type: ignore[valid-type]
    table_name: str,
    current_user: User = Depends(_require_admin),
) -> DictionaryTable:
    try:
        return _service.get_table(table_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{table_name}", response_model=DictionaryTable)
def upsert_dictionary(  # type: ignore[valid-type]
    table_name: str,
    payload: DictionaryTable,
    current_user: User = Depends(_require_admin),
) -> DictionaryTable:
    if payload.table.strip() != table_name.strip():
        raise HTTPException(status_code=400, detail="Le nom de table ne correspond pas.")
    try:
        return _service.upsert_table(payload)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{table_name}", status_code=204)
def delete_dictionary(  # type: ignore[valid-type]
    table_name: str,
    current_user: User = Depends(_require_admin),
) -> Response:
    try:
        _service.delete_table(table_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)
