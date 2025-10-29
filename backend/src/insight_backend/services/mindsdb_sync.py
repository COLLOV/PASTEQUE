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
            log.info("Uploading %s to MindsDB", p)
            client.upload_file(p)
            uploaded.append(p.name)
    finally:
        client.close()
    if not uploaded:
        log.info("No tables found in %s", repo.tables_dir)
    else:
        log.info("Uploaded %d tables to MindsDB", len(uploaded))
    return uploaded
