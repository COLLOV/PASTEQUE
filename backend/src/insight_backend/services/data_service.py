from ..schemas.data import IngestResponse
from ..schemas.tables import TableInfo, ColumnInfo
from ..repositories.data_repository import DataRepository
from ..core.config import settings
from pathlib import Path


class DataService:
    """Gère l’ingestion et la préparation des données."""

    def __init__(self, repo: DataRepository | None = None):
        self.repo = repo or DataRepository(tables_dir=Path(settings.tables_dir))

    def ingest(self, *, path: str | None = None, bytes_: bytes | None = None) -> IngestResponse:  # type: ignore[valid-type]
        raise NotImplementedError

    def list_tables(self) -> list[TableInfo]:
        names = self.repo.list_tables()
        infos: list[TableInfo] = []
        for n in names:
            p = self.repo._resolve_table_path(n)  # internal helper is fine here
            infos.append(TableInfo(name=n, path=str(p) if p else ""))
        return infos

    def get_schema(self, table_name: str) -> list[ColumnInfo]:
        cols = self.repo.get_schema(table_name)
        return [ColumnInfo(name=name, dtype=dtype) for name, dtype in cols]
