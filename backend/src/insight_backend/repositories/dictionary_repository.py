from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Any

import yaml


log = logging.getLogger("insight.repositories.dictionary")


class DataDictionaryRepository:
    """Load table/column definitions from YAML files stored on disk.

    Directory layout (config: DATA_DICTIONARY_DIR, default: ../data/dictionnary):
      - <table>.yml or <table>.yaml per table present in DATA_TABLES_DIR

    Minimal schema for a file:
    ---
    version: 1
    table: tickets_jira
    title: Tickets Jira
    description: Tickets d'incidents JIRA
    columns:
      - name: ticket_id
        description: Identifiant unique du ticket
        type: integer
        synonyms: [id, issue_id]
        unit: null
        pii: false
        example: "12345"
      - name: created_at
        description: Date de création (YYYY-MM-DD)
        type: date
        pii: false
    """

    def __init__(self, *, directory: str | Path):
        self.root = Path(directory)

    def _load_file(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return None
            return data
        except FileNotFoundError:
            return None
        except Exception:
            log.warning("Failed to read dictionary file: %s", path, exc_info=True)
            return None

    def _candidates(self, table: str) -> List[Path]:
        name = table.strip()
        return [self.root / f"{name}.yml", self.root / f"{name}.yaml"]

    def load_table(self, table: str) -> dict[str, Any] | None:
        for p in self._candidates(table):
            data = self._load_file(p)
            if data:
                return data
        return None

    def for_schema(self, schema: Dict[str, List[str]]) -> Dict[str, Any]:
        """Return a compact dictionary (JSON-serializable) limited to the given schema.

        Keeps only columns that exist in the provided schema to avoid noise.
        Output shape:
          { table: { description: str?, title: str?, columns: [{name, description?, type?, synonyms?, unit?, pii?, example?}] } }
        """
        out: Dict[str, Any] = {}
        for table, cols in schema.items():
            raw = self.load_table(table)
            if not raw:
                continue
            col_docs = []
            items = raw.get("columns") or []
            if not isinstance(items, list):
                items = []
            # Build lookup to avoid O(n^2)
            wanted = {c.casefold() for c in cols}
            for it in items:
                try:
                    name = str(it.get("name", "")).strip()
                    if not name or name.casefold() not in wanted:
                        continue
                    col_docs.append(
                        {
                            "name": name,
                            **({"description": str(it.get("description"))} if it.get("description") else {}),
                            **({"type": str(it.get("type"))} if it.get("type") else {}),
                            **({"synonyms": list(it.get("synonyms"))} if isinstance(it.get("synonyms"), list) else {}),
                            **({"unit": str(it.get("unit"))} if it.get("unit") else {}),
                            **({"pii": bool(it.get("pii"))} if it.get("pii") is not None else {}),
                            **({"example": it.get("example")} if it.get("example") is not None else {}),
                        }
                    )
                except Exception:
                    # Be strict in prod, lenient in dev; here we just skip invalid entries
                    continue
            if not col_docs:
                continue
            out[table] = {
                **({"title": raw.get("title")} if raw.get("title") else {}),
                **({"description": raw.get("description")} if raw.get("description") else {}),
                "columns": col_docs,
            }
        return out

