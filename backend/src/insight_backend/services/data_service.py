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
class DimensionField:
    field: str
    label: str


@dataclass(frozen=True)
class DatasetConfig:
    title: str
    date: DimensionField | None = None
    department: DimensionField | None = None
    campaign: DimensionField | None = None
    domain: DimensionField | None = None


DATASET_CONFIGS: dict[str, DatasetConfig] = {
    "myfeelback_agences": DatasetConfig(
        title="Feedback agences",
        date=DimensionField("date_feedback", "Date du feedback"),
        department=DimensionField("agence", "Agence"),
        domain=DimensionField("motif_visite", "Motif de visite"),
    ),
    "myfeelback_app_mobile": DatasetConfig(
        title="App mobile",
        date=DimensionField("date_feedback", "Date du feedback"),
        campaign=DimensionField("type_feedback", "Type de feedback"),
        domain=DimensionField("fonctionnalite", "Fonctionnalité"),
    ),
    "myfeelback_nps": DatasetConfig(
        title="NPS",
        date=DimensionField("date_feedback", "Date du feedback"),
        campaign=DimensionField("categorie", "Segment NPS"),
        domain=DimensionField("profil_client", "Profil client"),
    ),
    "myfeelback_remboursements": DatasetConfig(
        title="Remboursements",
        date=DimensionField("date_declaration", "Date de déclaration"),
        department=DimensionField("departement", "Département"),
        campaign=DimensionField("statut", "Statut du dossier"),
        domain=DimensionField("type_sinistre", "Type de sinistre"),
    ),
    "myfeelback_service_client": DatasetConfig(
        title="Service client",
        date=DimensionField("date_feedback", "Date du feedback"),
        department=DimensionField("canal", "Canal"),
        campaign=DimensionField("motif_contact", "Motif de contact"),
    ),
    "myfeelback_souscriptions": DatasetConfig(
        title="Souscriptions",
        date=DimensionField("date_feedback", "Date du feedback"),
        campaign=DimensionField("canal", "Canal de souscription"),
        domain=DimensionField("type_contrat", "Type de contrat"),
    ),
    "tickets_jira": DatasetConfig(
        title="Tickets Jira",
        date=DimensionField("creation_date", "Date de création"),
        department=DimensionField("departement", "Département"),
    ),
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
    dim: DimensionField | None,
    *,
    sort_by_label: bool = False,
) -> DimensionBreakdown | None:
    if not dim or not counter:
        return None
    if sort_by_label:
        items = sorted(counter.items(), key=lambda item: item[0])
    else:
        items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    counts = [DimensionCount(label=label, count=count) for label, count in items]
    return DimensionBreakdown(field=dim.field, label=dim.label, counts=counts)


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
            config = DATASET_CONFIGS.get(name, DatasetConfig(title=name))
            overview = self._compute_table_overview(table_name=name, config=config)
            if overview:
                sources.append(overview)

        return DataOverviewResponse(generated_at=datetime.utcnow(), sources=sources)

    def _compute_table_overview(
        self,
        *,
        table_name: str,
        config: DatasetConfig,
    ) -> DataSourceOverview | None:
        path = self.repo._resolve_table_path(table_name)
        if path is None:
            log.warning("Table introuvable pour l'overview: %s", table_name)
            return None

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        date_counter: Counter[str] = Counter()
        department_counter: Counter[str] = Counter()
        campaign_counter: Counter[str] = Counter()
        domain_counter: Counter[str] = Counter()
        total_rows = 0

        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            headers = set(reader.fieldnames or [])

            date_field = config.date if (config.date and config.date.field in headers) else None
            department_field = (
                config.department if (config.department and config.department.field in headers) else None
            )
            campaign_field = (
                config.campaign if (config.campaign and config.campaign.field in headers) else None
            )
            domain_field = config.domain if (config.domain and config.domain.field in headers) else None

            if config.date and not date_field:
                log.info("Colonne date absente pour %s: %s", table_name, config.date.field)
            if config.department and not department_field:
                log.info("Colonne département absente pour %s: %s", table_name, config.department.field)
            if config.campaign and not campaign_field:
                log.info("Colonne campagne absente pour %s: %s", table_name, config.campaign.field)
            if config.domain and not domain_field:
                log.info("Colonne domaine absente pour %s: %s", table_name, config.domain.field)

            for row in reader:
                total_rows += 1

                if date_field:
                    key = _normalize_date(row.get(date_field.field))
                    if key:
                        date_counter[key] += 1

                if department_field:
                    value = _clean_text(row.get(department_field.field))
                    if value:
                        department_counter[value] += 1

                if campaign_field:
                    value = _clean_text(row.get(campaign_field.field))
                    if value:
                        campaign_counter[value] += 1

                if domain_field:
                    value = _clean_text(row.get(domain_field.field))
                    if value:
                        domain_counter[value] += 1

        return DataSourceOverview(
            source=table_name,
            title=config.title or table_name,
            total_rows=total_rows,
            date=_build_dimension(date_counter, date_field, sort_by_label=True),
            department=_build_dimension(department_counter, department_field),
            campaign=_build_dimension(campaign_counter, campaign_field),
            domain=_build_dimension(domain_counter, domain_field),
        )
