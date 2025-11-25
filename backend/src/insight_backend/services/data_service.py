import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import csv

from ..schemas.data import IngestResponse, DataOverviewResponse, DataSourceOverview, FieldBreakdown, ValueCount
from ..schemas.tables import TableInfo, ColumnInfo
from ..repositories.data_repository import DataRepository
from ..core.config import settings


log = logging.getLogger("insight.services.data")


TABLE_TITLES: dict[str, str] = {
    "myfeelback_agences": "Feedback agences",
    "myfeelback_app_mobile": "App mobile",
    "myfeelback_nps": "NPS",
    "myfeelback_remboursements": "Remboursements",
    "myfeelback_service_client": "Service client",
    "myfeelback_souscriptions": "Souscriptions",
    "tickets_jira": "Tickets Jira",
}

MAX_VALUES_PER_FIELD = 30
DATE_CONFIDENCE_RATIO = 0.55
DATE_FIELD_HINT = "date"


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


@dataclass
class FieldAccumulator:
    name: str
    raw_counter: Counter[str] = field(default_factory=Counter)
    date_counter: Counter[str] = field(default_factory=Counter)
    non_null: int = 0
    parsed_dates: int = 0

    def add(self, value: object | None) -> None:
        text = _clean_text(value)
        if text is None:
            return

        self.non_null += 1

        normalized_date = _normalize_date(text)
        if normalized_date:
            self.parsed_dates += 1
            self.date_counter[normalized_date] += 1

        self.raw_counter[text] += 1

    def build_breakdown(self, *, total_rows: int) -> FieldBreakdown:
        """Convert the accumulated values into a serializable breakdown."""

        kind = "text"
        counter = self.raw_counter

        if self.date_counter and self.non_null:
            date_ratio = self.parsed_dates / self.non_null
            if date_ratio >= DATE_CONFIDENCE_RATIO or DATE_FIELD_HINT in self.name.lower():
                kind = "date"
                counter = self.date_counter

        if kind == "date":
            items = sorted(counter.items(), key=lambda item: item[0])
            if len(items) > MAX_VALUES_PER_FIELD:
                items = items[-MAX_VALUES_PER_FIELD:]
                truncated = True
            else:
                truncated = False
        else:
            items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
            if len(items) > MAX_VALUES_PER_FIELD:
                items = items[:MAX_VALUES_PER_FIELD]
                truncated = True
            else:
                truncated = False

        counts = [ValueCount(label=label, count=count) for label, count in items]
        missing_values = max(total_rows - self.non_null, 0)

        return FieldBreakdown(
            field=self.name,
            label=self.name,
            kind=kind,
            non_null=self.non_null,
            missing_values=missing_values,
            unique_values=len(counter),
            counts=counts,
            truncated=truncated,
        )


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

    def get_overview(self, *, allowed_tables: Iterable[str] | None = None) -> DataOverviewResponse:
        table_names = self.repo.list_tables()
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            table_names = [name for name in table_names if name.casefold() in allowed_set]
            log.debug("Filtered overview tables with permissions (count=%d)", len(table_names))

        sources: list[DataSourceOverview] = []
        for name in table_names:
            overview = self._compute_table_overview(table_name=name)
            if overview:
                sources.append(overview)

        return DataOverviewResponse(generated_at=datetime.now(timezone.utc), sources=sources)

    def _compute_table_overview(self, *, table_name: str) -> DataSourceOverview | None:
        path = self.repo._resolve_table_path(table_name)
        if path is None:
            log.warning("Table introuvable pour l'overview: %s", table_name)
            return None

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        total_rows = 0

        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = reader.fieldnames or []
            if not headers:
                log.info("Aucune colonne détectée pour %s, rien à afficher.", table_name)
                return DataSourceOverview(
                    source=table_name,
                    title=TABLE_TITLES.get(table_name, table_name),
                    total_rows=0,
                    fields=[],
                )

            accumulators = {name: FieldAccumulator(name=name) for name in headers}

            for row in reader:
                total_rows += 1
                for name, acc in accumulators.items():
                    acc.add(row.get(name))

        fields = [acc.build_breakdown(total_rows=total_rows) for acc in accumulators.values()]

        log.info(
            "Overview calculé pour %s : %d lignes, %d colonnes",
            table_name,
            total_rows,
            len(fields),
        )

        return DataSourceOverview(
            source=table_name,
            title=TABLE_TITLES.get(table_name, table_name),
            total_rows=total_rows,
            fields=fields,
        )
