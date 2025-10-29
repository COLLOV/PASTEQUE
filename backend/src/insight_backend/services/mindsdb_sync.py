from __future__ import annotations

import logging
from pathlib import Path

from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..repositories.data_repository import DataRepository


log = logging.getLogger("insight.services.mindsdb_sync")


def sync_all_tables() -> list[str]:
    repo = DataRepository(tables_dir=Path(settings.tables_dir))
    client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
    uploaded: list[str] = []
    try:
        for p in repo._iter_table_files():
            table_name = DataRepository.canonical_table_name(p.stem)
            log.info("Uploading %s to MindsDB as %s.%s", p, settings.nl2sql_db_prefix, table_name)
            client.upload_file(p, table_name=table_name)
            uploaded.append(f"{table_name}<-{p.name}")
    finally:
        client.close()
    if not uploaded:
        log.info("No tables found in %s", repo.tables_dir)
    else:
        log.info("Uploaded %d tables to MindsDB", len(uploaded))
    return uploaded
