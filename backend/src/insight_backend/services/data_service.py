import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping
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
from ..repositories.dictionary_repository import DataDictionaryRepository
from ..core.config import settings, resolve_project_path


log = logging.getLogger("insight.services.data")


@dataclass(frozen=True)
class ColumnSpec:
  field: str
  label: str
  kind: str


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
  spec: ColumnSpec,
) -> DimensionBreakdown | None:
  if not counter:
    return None
  items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
  counts = [DimensionCount(label=label, count=count) for label, count in items]
  return DimensionBreakdown(field=spec.field, label=spec.label, kind=spec.kind, counts=counts)


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
    hidden_columns: Mapping[str, set[str]] | None = None,
  ) -> DataOverviewResponse:
    table_names = self.repo.list_tables()
    if allowed_tables is not None:
      allowed_set = {name.casefold() for name in allowed_tables}
      table_names = [name for name in table_names if name.casefold() in allowed_set]
      log.debug("Filtered overview tables with permissions (count=%d)", len(table_names))

    # Build schema for all tables and load compact data dictionary
    schema: dict[str, list[str]] = {}
    for name in table_names:
      cols = [col for col, _ in self.repo.get_schema(name)]
      schema[name] = cols
    dico_repo = DataDictionaryRepository(
      directory=Path(resolve_project_path(settings.data_dictionary_dir))
    )
    dico = dico_repo.for_schema(schema)

    sources: list[DataSourceOverview] = []
    hidden_lookup = {k: {c.casefold() for c in v} for k, v in (hidden_columns or {}).items()}
    for name in table_names:
      overview = self._compute_table_overview(
        table_name=name,
        columns=schema.get(name, []),
        dico_table=dico.get(name) or {},
        hidden_columns=hidden_lookup.get(name, set()),
      )
      if overview:
        sources.append(overview)

    return DataOverviewResponse(generated_at=datetime.utcnow(), sources=sources)

  def _compute_table_overview(
    self,
    *,
    table_name: str,
    columns: list[str],
    dico_table: dict,
    hidden_columns: set[str],
  ) -> DataSourceOverview | None:
    path = self.repo._resolve_table_path(table_name)
    if path is None:
      log.warning("Table introuvable pour l'overview: %s", table_name)
      return None

    delimiter = "," if path.suffix.lower() == ".csv" else "\t"

    # Build specs per column using dictionary when available
    dico_cols = {}
    raw_cols = dico_table.get("columns") or []
    if isinstance(raw_cols, list):
      for it in raw_cols:
        try:
          name = str(it.get("name", "")).strip()
          if not name:
            continue
          dico_cols[name] = it
        except Exception:
          continue

    specs: list[ColumnSpec] = []
    for col in columns:
      if col.casefold() in hidden_columns:
        continue
      meta = dico_cols.get(col, {})
      label = (meta.get("description") or "").strip() or col
      raw_type = str(meta.get("type") or "").strip().lower()
      if raw_type in {"date", "datetime"}:
        kind = "date"
      elif raw_type in {"integer", "float", "number", "numeric"}:
        kind = "number"
      elif raw_type in {"boolean", "bool"}:
        kind = "boolean"
      else:
        kind = "category"
      specs.append(ColumnSpec(field=col, label=label, kind=kind))

    if not specs:
      log.info("Aucune colonne exploitable pour l'overview: %s", table_name)
      return DataSourceOverview(
        source=table_name,
        title=dico_table.get("title") or table_name,
        total_rows=0,
        dimensions=[],
      )

    counters: dict[str, Counter[str]] = {spec.field: Counter() for spec in specs}
    total_rows = 0

    with path.open("r", newline="", encoding="utf-8") as handle:
      reader = csv.DictReader(handle, delimiter=delimiter)
      for row in reader:
        total_rows += 1
        for spec in specs:
          raw = row.get(spec.field)
          if spec.kind == "date":
            key = _normalize_date(raw)
          else:
            key = _clean_text(raw)
          if key:
            counters[spec.field][key] += 1

    dimensions: list[DimensionBreakdown] = []
    for spec in specs:
      dim = _build_dimension(counters[spec.field], spec)
      if dim:
        dimensions.append(dim)

    return DataSourceOverview(
      source=table_name,
      title=dico_table.get("title") or table_name,
      total_rows=total_rows,
      dimensions=dimensions,
    )
