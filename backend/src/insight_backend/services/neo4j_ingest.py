from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime
from ..core.config import settings
from ..integrations.neo4j_client import Neo4jClient, Neo4jClientError


log = logging.getLogger("insight.services.neo4j_ingest")


class Neo4jIngestionError(RuntimeError):
    """Raised when Neo4j ingestion fails."""


@dataclass(frozen=True)
class ClientDatasetSpec:
    filename: str
    label: str
    key: str
    relationship: str
    date_field: Optional[str] = None
    source: str = "import"
    date_fields: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DepartmentDatasetSpec:
    filename: str
    label: str
    key: str
    department_field: str
    relationship: str
    source: str = "import"
    date_fields: Tuple[str, ...] = ()


class Neo4jIngestionService:
    """Load CSV data into Neo4j with deterministic labels and relationships."""

    _CLIENT_DATASETS: tuple[ClientDatasetSpec, ...] = (
        ClientDatasetSpec(
            filename="myfeelback_agences.csv",
            label="AgencyFeedback",
            key="feedback_id",
            relationship="HAS_AGENCY_FEEDBACK",
            date_field="date_feedback",
            source="myfeelback_agences",
            date_fields=("date_feedback",),
        ),
        ClientDatasetSpec(
            filename="myfeelback_app_mobile.csv",
            label="AppFeedback",
            key="feedback_id",
            relationship="HAS_APP_FEEDBACK",
            date_field="date_feedback",
            source="myfeelback_app_mobile",
            date_fields=("date_feedback",),
        ),
        ClientDatasetSpec(
            filename="myfeelback_nps.csv",
            label="NPSFeedback",
            key="feedback_id",
            relationship="HAS_NPS_FEEDBACK",
            date_field="date_feedback",
            source="myfeelback_nps",
            date_fields=("date_feedback",),
        ),
        ClientDatasetSpec(
            filename="myfeelback_service_client.csv",
            label="ServiceFeedback",
            key="feedback_id",
            relationship="HAS_SERVICE_FEEDBACK",
            date_field="date_feedback",
            source="myfeelback_service_client",
            date_fields=("date_feedback",),
        ),
        ClientDatasetSpec(
            filename="myfeelback_souscriptions.csv",
            label="SubscriptionFeedback",
            key="feedback_id",
            relationship="HAS_SUBSCRIPTION_FEEDBACK",
            date_field="date_feedback",
            source="myfeelback_souscriptions",
            date_fields=("date_feedback",),
        ),
        ClientDatasetSpec(
            filename="myfeelback_remboursements.csv",
            label="Claim",
            key="sinistre_id",
            relationship="HAS_CLAIM",
            date_field="date_declaration",
            source="myfeelback_remboursements",
            date_fields=("date_declaration", "date_remboursement"),
        ),
    )

    _DEPARTMENT_DATASETS: tuple[DepartmentDatasetSpec, ...] = (
        DepartmentDatasetSpec(
            filename="myfeelback_remboursements.csv",
            label="Claim",
            key="sinistre_id",
            department_field="departement",
            relationship="HANDLED_BY",
            source="myfeelback_remboursements",
        ),
        DepartmentDatasetSpec(
            filename="tickets_jira.csv",
            label="Ticket",
            key="ticket_id",
            department_field="departement",
            relationship="BELONGS_TO",
            source="tickets_jira",
        ),
    )

    def __init__(self, *, data_dir: Optional[Path] = None):
        raw_dir = Path(settings.data_root).resolve() / "raw"
        self.data_dir = Path(data_dir) if data_dir else raw_dir
        self.client = Neo4jClient(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database or None,
            max_rows=settings.neo4j_result_limit,
        )

    def close(self) -> None:
        self.client.close()

    def sync_all(self) -> Dict[str, int]:
        if not self.data_dir.exists():
            raise Neo4jIngestionError(f"Répertoire des données introuvable: {self.data_dir}")

        log.info("Démarrage de l'ingestion Neo4j depuis %s", self.data_dir)
        try:
            self._ensure_constraints()
            summary: Dict[str, int] = {}
            for spec in self._CLIENT_DATASETS:
                summary[spec.source] = self._ingest_client_dataset(spec)
            summary["tickets"] = self._ingest_tickets()
            self._link_departments()
            log.info("Ingestion Neo4j terminée: %s", summary)
            return summary
        finally:
            self.close()

    def _ensure_constraints(self) -> None:
        statements = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Client) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Department) REQUIRE d.name IS UNIQUE",
        ]
        for spec in self._CLIENT_DATASETS:
            statements.append(
                f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{spec.label}) REQUIRE n.{spec.key} IS UNIQUE"
            )
        statements.append(
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Ticket) REQUIRE t.ticket_id IS UNIQUE"
        )
        self.client.ensure(statements)

    def _ingest_client_dataset(self, spec: ClientDatasetSpec) -> int:
        rows = self._read_csv(spec.filename)
        if not rows:
            log.warning("Aucune donnée trouvée pour %s", spec.filename)
            return 0

        payload: List[Dict[str, object]] = []
        for raw in rows:
            identifier = raw.get(spec.key)
            client_id = self._clean_value(raw.get("client_id"))
            if not identifier:
                continue
            props = self._prepare_props(raw, date_fields=spec.date_fields, skip_fields={"client_id"})
            props["source"] = spec.source
            payload.append(
                {
                    "id": identifier,
                    "props": props,
                    "client_id": client_id,
                    "last_seen": props.get(spec.date_field) if spec.date_field else None,
                    "source": spec.source,
                }
            )

        if not payload:
            return 0

        query = f"""
        UNWIND $rows AS row
        MERGE (n:{spec.label} {{{spec.key}: row.id}})
        SET n += row.props
        FOREACH (_ IN CASE WHEN row.client_id IS NULL THEN [] ELSE [1] END |
            MERGE (c:Client {{id: row.client_id}})
            SET c.last_seen = CASE WHEN row.last_seen IS NOT NULL THEN row.last_seen ELSE c.last_seen END
            MERGE (c)-[rel:{spec.relationship}]->(n)
            SET rel.source = row.source
        )
        """
        self.client.run_write(query, parameters={"rows": payload})
        log.info("Ingestion dataset %s -> %d lignes", spec.filename, len(payload))
        return len(payload)

    def _ingest_tickets(self) -> int:
        rows = self._read_csv("tickets_jira.csv")
        if not rows:
            log.warning("Aucune donnée trouvée pour tickets_jira.csv")
            return 0
        payload: List[Dict[str, object]] = []
        for raw in rows:
            ticket_id = raw.get("ticket_id")
            if not ticket_id:
                continue
            props = self._prepare_props(raw, date_fields=("creation_date",), skip_fields=set())
            props["source"] = "tickets_jira"
            payload.append(
                {
                    "id": ticket_id,
                    "props": props,
                    "department": props.get("departement"),
                    "created_at": props.get("creation_date"),
                }
            )
        if not payload:
            return 0

        query = """
        UNWIND $rows AS row
        MERGE (t:Ticket {ticket_id: row.id})
        SET t += row.props
        FOREACH (_ IN CASE WHEN row.department IS NULL THEN [] ELSE [1] END |
            MERGE (d:Department {name: row.department})
            MERGE (t)-[:BELONGS_TO]->(d)
        )
        """
        self.client.run_write(query, parameters={"rows": payload})
        log.info("Ingestion tickets -> %d lignes", len(payload))
        return len(payload)

    def _link_departments(self) -> None:
        for spec in self._DEPARTMENT_DATASETS:
            rows = self._read_csv(spec.filename)
            if not rows:
                continue
            payload = []
            for raw in rows:
                identifier = raw.get(spec.key)
                department = self._clean_value(raw.get(spec.department_field))
                if not identifier or not department:
                    continue
                payload.append(
                    {
                        "id": identifier,
                        "department": department,
                        "source": spec.source,
                    }
                )
            if not payload:
                continue
            query = f"""
            UNWIND $rows AS row
            MATCH (n:{spec.label} {{{spec.key}: row.id}})
            MERGE (d:Department {{name: row.department}})
            MERGE (n)-[rel:{spec.relationship}]->(d)
            SET rel.source = row.source
            """
            self.client.run_write(query, parameters={"rows": payload})
            log.info("Relations %s -> Department: %d", spec.label, len(payload))

    @staticmethod
    def _prepare_props(
        row: Dict[str, str],
        *,
        date_fields: Tuple[str, ...],
        skip_fields: set[str],
    ) -> Dict[str, object]:
        props: Dict[str, object] = {}
        for key, raw in row.items():
            if key in skip_fields:
                continue
            props[key] = Neo4jIngestionService._coerce_value(key, raw, date_fields)
        return props

    @staticmethod
    def _coerce_value(key: str, value: Optional[str], date_fields: Tuple[str, ...]) -> object:
        text = Neo4jIngestionService._clean_value(value)
        if text is None:
            return None

        if key in date_fields:
            try:
                if len(text) == 10:
                    return date.fromisoformat(text)
                return datetime.fromisoformat(text).date()
            except ValueError:
                log.debug("Neo4j ingestion: failed to parse date for %s=%s", key, text)
                return text

        try:
            if text.startswith("-") and text[1:].isdigit():
                return int(text)
            if text.isdigit():
                return int(text)
        except ValueError:
            pass
        return text

    def _read_csv(self, name: str) -> List[Dict[str, str]]:
        path = self.data_dir / name
        if not path.exists():
            log.warning("Fichier CSV manquant pour Neo4j: %s", path)
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    @staticmethod
    def _clean_value(value: str | None) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


def sync_all() -> Dict[str, int]:
    service = Neo4jIngestionService()
    try:
        return service.sync_all()
    except (Neo4jClientError, Neo4jIngestionError) as exc:
        log.error("Échec de l'ingestion Neo4j: %s", exc)
        raise
