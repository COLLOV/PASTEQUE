import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
import csv

from ..schemas.data import (
    IngestResponse,
    DataOverviewResponse,
    DataSourceOverview,
    DimensionBreakdown,
    DimensionCount,
)
from ..schemas.tables import TableInfo, ColumnInfo
from ..repositories.data_repository import DataRepository
from ..core.config import settings


log = logging.getLogger("insight.services.data")


@dataclass(frozen=True)
class DatasetConfig:
    title: str | None = None


DATASET_CONFIGS: dict[str, DatasetConfig] = {
    "myfeelback_agences": DatasetConfig(title="Feedback agences"),
    "myfeelback_app_mobile": DatasetConfig(title="App mobile"),
    "myfeelback_nps": DatasetConfig(title="NPS"),
    "myfeelback_remboursements": DatasetConfig(title="Remboursements"),
    "myfeelback_service_client": DatasetConfig(title="Service client"),
    "myfeelback_souscriptions": DatasetConfig(title="Souscriptions"),
    "tickets_jira": DatasetConfig(title="Tickets Jira"),
}


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_date(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace(" ", "T"))
        return dt.date().isoformat()
    except ValueError:
        log.debug("Impossible de parser la date %r", text)
        return None


def _build_dimension(
    counter: Counter[str],
    field: str,
    label: str | None = None,
    *,
    sort_by_label: bool = False,
) -> DimensionBreakdown | None:
    if not counter:
        return None
    if sort_by_label:
        items = sorted(counter.items(), key=lambda item: item[0])
    else:
        items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    counts = [DimensionCount(label=value, count=count) for value, count in items]
    dim_label = label or field
    return DimensionBreakdown(field=field, label=dim_label, counts=counts)


class DataService:
    """Gère l’ingestion et la préparation des données."""

    def __init__(self, repo: DataRepository | None = None):
        self.repo = repo or DataRepository(tables_dir=Path(settings.tables_dir))

    def ingest(self, *, path: str | None = None, bytes_: bytes | None = None) -> IngestResponse:  # type: ignore[valid-type]
        raise NotImplementedError

    def list_tables(self, *, allowed_tables: Iterable[str] | None = None) -> list[TableInfo]:
        names = self.repo.list_tables()
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            names = [n for n in names if n.casefold() in allowed_set]
            log.debug("Filtered tables with permissions (count=%d)", len(names))
        infos: list[TableInfo] = []
        for n in names:
            p = self.repo._resolve_table_path(n)  # internal helper is fine here
            infos.append(TableInfo(name=n, path=str(p) if p else ""))
        return infos

    def get_schema(self, table_name: str, *, allowed_tables: Iterable[str] | None = None) -> list[ColumnInfo]:
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            if table_name.casefold() not in allowed_set:
                log.warning("Permission denied for schema access table=%s", table_name)
                raise PermissionError(f"Access to table '{table_name}' is not permitted")
        cols = self.repo.get_schema(table_name)
        return [ColumnInfo(name=name, dtype=dtype) for name, dtype in cols]

    def get_overview(
        self,
        *,
        allowed_tables: Iterable[str] | None = None,
        hidden_columns: dict[str, set[str]] | None = None,
    ) -> DataOverviewResponse:
        table_names = self.repo.list_tables()
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            table_names = [name for name in table_names if name.casefold() in allowed_set]
            log.debug("Filtered overview tables with permissions (count=%d)", len(table_names))

        hidden_lookup = hidden_columns or {}
        sources: list[DataSourceOverview] = []
        for name in table_names:
            config = DATASET_CONFIGS.get(name, DatasetConfig())
            overview = self._compute_table_overview(
                table_name=name,
                title=config.title or name,
                hidden_columns=hidden_lookup.get(name),
            )
            if overview:
                sources.append(overview)

        return DataOverviewResponse(generated_at=datetime.utcnow(), sources=sources)

    def _compute_table_overview(
        self,
        *,
        table_name: str,
        title: str,
        hidden_columns: set[str] | None = None,
    ) -> DataSourceOverview | None:
        path = self.repo._resolve_table_path(table_name)
        if path is None:
            log.warning("Table introuvable pour l'overview: %s", table_name)
            return None

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        total_rows = 0
        hidden = {name.casefold() for name in hidden_columns} if hidden_columns else set()
        dimensions: list[DimensionBreakdown] = []

        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = [h for h in (reader.fieldnames or []) if h and h.casefold() not in hidden]
            counters: dict[str, Counter[str]] = {name: Counter() for name in headers}

            for row in reader:
                total_rows += 1
                for field in headers:
                    raw = row.get(field)
                    if raw is None:
                        continue
                    field_lower = field.casefold()
                    if "date" in field_lower:
                        key = _normalize_date(raw)
                    else:
                        key = _clean_text(raw)
                    if key:
                        counters[field][key] += 1

        for field in headers:
            counter = counters.get(field)
            if not counter:
                continue
            is_date_dimension = "date" in field.casefold()
            dim = _build_dimension(counter, field=field, label=None, sort_by_label=is_date_dimension)
            if dim:
                dimensions.append(dim)

        log.info(
            "Computed overview for table=%s rows=%d columns=%d (visible)",
            table_name,
            total_rows,
            len(dimensions),
        )

        return DataSourceOverview(
            source=table_name,
            title=title or table_name,
            total_rows=total_rows,
            columns=dimensions,
        )
