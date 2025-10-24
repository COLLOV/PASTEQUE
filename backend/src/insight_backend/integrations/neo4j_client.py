from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Relationship


def _is_primitive(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _serialize_value(value: Any) -> Any:
    if _is_primitive(value):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, Node):
        payload: Dict[str, Any] = {
            "id": value.element_id,
            "labels": sorted(value.labels),
        }
        payload.update({k: _serialize_value(v) for k, v in value.items()})
        return payload
    if isinstance(value, Relationship):
        payload = {
            "id": value.element_id,
            "type": value.type,
            "start": value.start_node.element_id,
            "end": value.end_node.element_id,
        }
        payload.update({k: _serialize_value(v) for k, v in value.items()})
        return payload
    if hasattr(value, "_fields"):  # neo4j Record or namedtuple-like
        return {k: _serialize_value(getattr(value, k)) for k in value._fields}
    return str(value)


class Neo4jClientError(RuntimeError):
    """Raised when the Neo4j client encounters an error."""


@dataclass(slots=True)
class Neo4jResult:
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int


@dataclass
class Neo4jClient:
    """Lightweight Neo4j driver wrapper for read/write helpers."""

    uri: str
    username: str
    password: str
    database: Optional[str] = None
    max_rows: int = 200

    def __post_init__(self) -> None:
        try:
            self._driver: Driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
            )
        except Neo4jError as exc:  # pragma: no cover - driver init depends on external service
            raise Neo4jClientError(str(exc)) from exc

    def close(self) -> None:
        self._driver.close()

    def run_write(self, cypher: str, *, parameters: Optional[Dict[str, Any]] = None) -> None:
        def work(tx: Any) -> None:
            tx.run(cypher, **(parameters or {})).consume()

        try:
            with self._driver.session(database=self.database) as session:
                session.execute_write(work)
        except Neo4jError as exc:
            raise Neo4jClientError(str(exc)) from exc

    def run_read(
        self,
        cypher: str,
        *,
        parameters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Neo4jResult:
        def work(tx: Any) -> Neo4jResult:
            result = tx.run(cypher, **(parameters or {}))
            keys = list(result.keys())
            rows: List[Dict[str, Any]] = []
            cap = limit or self.max_rows
            for record in result:
                row = {key: _serialize_value(record.get(key)) for key in keys}
                rows.append(row)
                if cap and len(rows) >= cap:
                    break
            return Neo4jResult(columns=keys, rows=rows, row_count=len(rows))

        try:
            with self._driver.session(database=self.database) as session:
                return session.execute_read(work)
        except Neo4jError as exc:
            raise Neo4jClientError(str(exc)) from exc

    def ensure(self, statements: Iterable[str]) -> None:
        """Execute DDL statements idempotently."""
        for stmt in statements:
            if not stmt.strip():
                continue
            self.run_write(stmt)
