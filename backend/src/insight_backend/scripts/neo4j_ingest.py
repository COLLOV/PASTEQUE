from __future__ import annotations

import sys

from ..integrations.neo4j_client import Neo4jClientError
from ..services.neo4j_ingest import Neo4jIngestionError, Neo4jIngestionService


def main() -> None:
    service = Neo4jIngestionService()
    try:
        summary = service.sync_all()
    except (Neo4jIngestionError, Neo4jClientError) as exc:
        print(f"[neo4j_ingest] ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - depends on external service
        print(f"[neo4j_ingest] ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not summary:
        print("[neo4j_ingest] Aucun enregistrement importé.")
    else:
        for key, count in summary.items():
            print(f"[neo4j_ingest] {key}: {count}")


if __name__ == "__main__":
    main()
