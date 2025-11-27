import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Collection, Iterable, Mapping
import csv

from ..schemas.data import (
    IngestResponse,
    DataOverviewResponse,
    DataSourceOverview,
    FieldBreakdown,
    ValueCount,
    CategorySubCategoryCount,
    TableExplorePreview,
)
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
CATEGORY_COLUMN_NAME = "Category"
SUB_CATEGORY_COLUMN_NAME = "Sub Category"


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

    def get_overview(
        self,
        *,
        allowed_tables: Iterable[str] | None = None,
        hidden_fields_by_source: Mapping[str, Iterable[str]] | None = None,
        include_hidden_fields: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> DataOverviewResponse:
        table_names = self.repo.list_tables()
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            table_names = [name for name in table_names if name.casefold() in allowed_set]
            log.debug("Filtered overview tables with permissions (count=%d)", len(table_names))

        normalized_from = _normalize_date(date_from) if date_from else None
        normalized_to = _normalize_date(date_to) if date_to else None
        if date_from and not normalized_from:
            raise ValueError("Paramètre 'date_from' invalide (format attendu ISO 8601).")
        if date_to and not normalized_to:
            raise ValueError("Paramètre 'date_to' invalide (format attendu ISO 8601).")

        hidden_lookup: Mapping[str, set[str]] = {
            (name.casefold() if hasattr(name, "casefold") else str(name)): set(fields)
            for name, fields in (hidden_fields_by_source or {}).items()
        }

        sources: list[DataSourceOverview] = []
        for name in table_names:
            hidden_for_table = hidden_lookup.get(name.casefold(), set())
            overview = self._compute_table_overview(
                table_name=name,
                hidden_fields=hidden_for_table,
                include_hidden_fields=include_hidden_fields,
                date_from=normalized_from,
                date_to=normalized_to,
            )
            if overview:
                sources.append(overview)

        return DataOverviewResponse(generated_at=datetime.now(timezone.utc), sources=sources)

    def _compute_table_overview(
        self,
        *,
        table_name: str,
        hidden_fields: Collection[str] | None = None,
        include_hidden_fields: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> DataSourceOverview | None:
        path = self.repo._resolve_table_path(table_name)
        if path is None:
            log.warning("Table introuvable pour l'overview: %s", table_name)
            return None

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        total_rows = 0
        date_min: str | None = None
        date_max: str | None = None
        date_from_norm = date_from
        date_to_norm = date_to

        category_pairs: Counter[tuple[str, str]] = Counter()
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = reader.fieldnames or []
            if not headers:
                log.info("Aucune colonne détectée pour %s, rien à afficher.", table_name)
                return DataSourceOverview(
                    source=table_name,
                    title=TABLE_TITLES.get(table_name, table_name),
                    total_rows=0,
                    field_count=0,
                    fields=[],
                )

            accumulators = {name: FieldAccumulator(name=name) for name in headers}

            category_field = None
            sub_category_field = None
            date_field = None
            for name in headers:
                if name == CATEGORY_COLUMN_NAME:
                    category_field = name
                if name == SUB_CATEGORY_COLUMN_NAME:
                    sub_category_field = name
                if name.casefold() == "date":
                    date_field = name

            if (date_from_norm or date_to_norm) and not date_field:
                raise ValueError("Colonne 'date' requise pour filtrer l'overview par date.")

            for row in reader:
                normalized_date = _normalize_date(row.get(date_field)) if date_field else None
                if normalized_date:
                    if date_min is None or normalized_date < date_min:
                        date_min = normalized_date
                    if date_max is None or normalized_date > date_max:
                        date_max = normalized_date

                if date_from_norm or date_to_norm:
                    if normalized_date is None:
                        continue
                    if date_from_norm and normalized_date < date_from_norm:
                        continue
                    if date_to_norm and normalized_date > date_to_norm:
                        continue

                total_rows += 1
                for name, acc in accumulators.items():
                    acc.add(row.get(name))
                if category_field and sub_category_field:
                    category_value = _clean_text(row.get(category_field))
                    sub_category_value = _clean_text(row.get(sub_category_field))
                    if category_value and sub_category_value:
                        category_pairs[(category_value, sub_category_value)] += 1

        fields = [acc.build_breakdown(total_rows=total_rows) for acc in accumulators.values()]
        hidden_set = set(hidden_fields or [])
        for item in fields:
            item.hidden = item.field in hidden_set

        total_field_count = len(fields)
        if hidden_set and not include_hidden_fields:
            fields = [item for item in fields if item.field not in hidden_set]

        visible_count = len(fields)
        category_breakdown: list[CategorySubCategoryCount] = []
        if category_pairs:
            items = sorted(category_pairs.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
            if len(items) > MAX_VALUES_PER_FIELD:
                items = items[:MAX_VALUES_PER_FIELD]
            category_breakdown = [
                CategorySubCategoryCount(category=cat, sub_category=sub, count=count)
                for (cat, sub), count in items
            ]

        log.info(
            "Overview calculé pour %s : %d lignes, colonnes visibles=%d / total=%d, couples Category/Sub=%d",
            table_name,
            total_rows,
            visible_count,
            total_field_count,
            len(category_breakdown),
            date_from_norm,
            date_to_norm,
        )

        return DataSourceOverview(
            source=table_name,
            title=TABLE_TITLES.get(table_name, table_name),
            total_rows=total_rows,
            date_min=date_min,
            date_max=date_max,
            field_count=total_field_count,
            fields=fields,
            category_breakdown=category_breakdown,
        )

    def explore_table(
        self,
        *,
        table_name: str,
        category: str,
        sub_category: str,
        limit: int = 25,
        offset: int = 0,
        sort_date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        allowed_tables: Iterable[str] | None = None,
    ) -> TableExplorePreview:
        if allowed_tables is not None:
            allowed_set = {name.casefold() for name in allowed_tables}
            if table_name.casefold() not in allowed_set:
                log.warning("Permission denied for explore access table=%s", table_name)
                raise PermissionError(f"Access to table '{table_name}' is not permitted")

        if limit < 1 or limit > 500:
            raise ValueError("Paramètre 'limit' invalide (doit être entre 1 et 500)")
        if offset < 0:
            raise ValueError("Paramètre 'offset' invalide (doit être >= 0)")

        path = self.repo._resolve_table_path(table_name)
        if path is None:
            log.warning("Table introuvable pour l'explore: %s", table_name)
            raise FileNotFoundError(f"Table introuvable: {table_name}")

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        matching_rows = 0
        matched_rows: list[dict[str, str | int | float | bool | None]] = []

        normalized_from = _normalize_date(date_from) if date_from else None
        normalized_to = _normalize_date(date_to) if date_to else None
        if date_from and not normalized_from:
            raise ValueError("Paramètre 'date_from' invalide (format attendu ISO 8601).")
        if date_to and not normalized_to:
            raise ValueError("Paramètre 'date_to' invalide (format attendu ISO 8601).")

        date_domain_min: str | None = None
        date_domain_max: str | None = None

        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = reader.fieldnames or []
            if not headers:
                log.info("Aucune colonne détectée pour %s, rien à explorer.", table_name)
                return TableExplorePreview(
                    source=table_name,
                    category=category,
                    sub_category=sub_category,
                    matching_rows=0,
                    preview_columns=[],
                    preview_rows=[],
                    limit=limit,
                    offset=offset,
                    sort_date=sort_date,
                )

            if CATEGORY_COLUMN_NAME not in headers or SUB_CATEGORY_COLUMN_NAME not in headers:
                raise ValueError(
                    f"Colonnes requises manquantes pour l'exploration: "
                    f"{CATEGORY_COLUMN_NAME!r} et {SUB_CATEGORY_COLUMN_NAME!r}"
                )

            sort_direction = None
            if sort_date:
                normalized_sort = sort_date.strip().casefold()
                if normalized_sort not in {"asc", "desc"}:
                    raise ValueError("Paramètre 'sort_date' invalide (attendu: asc ou desc)")
                sort_direction = normalized_sort

            date_column = None
            if sort_direction or normalized_from or normalized_to:
                for name in headers:
                    if name.casefold() == "date":
                        date_column = name
                        break
                if date_column is None:
                    raise ValueError("Colonne 'date' introuvable pour appliquer tri/filtre.")

            for row in reader:
                cat_value = _clean_text(row.get(CATEGORY_COLUMN_NAME))
                sub_value = _clean_text(row.get(SUB_CATEGORY_COLUMN_NAME))
                if cat_value == category and sub_value == sub_category:
                    normalized_value = _normalize_date(row.get(date_column)) if date_column else None
                    if normalized_value:
                        if date_domain_min is None or normalized_value < date_domain_min:
                            date_domain_min = normalized_value
                        if date_domain_max is None or normalized_value > date_domain_max:
                            date_domain_max = normalized_value

                    if date_column and (normalized_from or normalized_to):
                        if normalized_value is None:
                            continue
                        if normalized_from and normalized_value < normalized_from:
                            continue
                        if normalized_to and normalized_value > normalized_to:
                            continue
                    matching_rows += 1
                    matched_rows.append(row)  # type: ignore[arg-type]

        if sort_direction and date_column:
            def _sort_key(row: Mapping[str, object | None]) -> str:
                normalized = _normalize_date(row.get(date_column))
                if normalized:
                    return normalized
                fallback = _clean_text(row.get(date_column))
                return fallback or ""

            matched_rows.sort(key=_sort_key, reverse=sort_direction == "desc")

        preview_rows = matched_rows[offset : offset + limit]

        log.info(
            "Explore table %s pour Category=%s, Sub Category=%s : lignes=%d, aperçu=%d (offset=%d, limit=%d, sort_date=%s, date_from=%s, date_to=%s)",
            table_name,
            category,
            sub_category,
            matching_rows,
            len(preview_rows),
            offset,
            limit,
            sort_direction,
            normalized_from,
            normalized_to,
        )

        return TableExplorePreview(
            source=table_name,
            category=category,
            sub_category=sub_category,
            matching_rows=matching_rows,
            preview_columns=headers,
            preview_rows=preview_rows,
            limit=limit,
            offset=offset,
            sort_date=sort_direction,
            date_from=normalized_from,
            date_to=normalized_to,
            date_min=date_domain_min,
            date_max=date_domain_max,
        )
