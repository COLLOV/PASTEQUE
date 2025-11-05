from __future__ import annotations

from pathlib import Path

from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..repositories.data_repository import DataRepository


def verify_mindsdb_tables() -> int:
    repo = DataRepository(tables_dir=Path(settings.tables_dir))
    tables = [p.stem for p in repo._iter_table_files()]
    client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
    prefix = settings.nl2sql_db_prefix or "files"
    errors = 0
    try:
        for t in tables:
            try:
                data = client.sql(f"SELECT COUNT(*) AS n FROM {prefix}.{t}")
                cols = data.get("column_names") or data.get("columns") or []
                rows = data.get("data") or data.get("rows") or []
                count = 0
                if rows:
                    if isinstance(rows[0], dict):
                        count = int(rows[0].get("n") or next(iter(rows[0].values())))
                    else:
                        count = int(rows[0][0])
                print(f"[start] {prefix}.{t}: {count} row(s)")
            except Exception as exc:  # pragma: no cover - diagnostic utility
                errors += 1
                print(f"[start] ERROR verifying {prefix}.{t}: {exc}")
    finally:
        client.close()
    if errors:
        print(f"[start] WARNING: {errors} table(s) failed verification.")
    return errors


def main() -> None:  # pragma: no cover - CLI utility
    verify_mindsdb_tables()


if __name__ == "__main__":  # pragma: no cover - CLI utility
    main()

