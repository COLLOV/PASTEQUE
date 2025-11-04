from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import httpx


class MindsDBClient:
    """Minimal HTTP client for MindsDB OSS.

    Supports:
    - Uploading local files to the built‑in `files` database.
    - Executing SQL queries via REST API.
    """

    def __init__(self, *, base_url: str, token: Optional[str] = None, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = httpx.Client(timeout=timeout_s)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def upload_file(self, path: str | Path, *, table_name: str | None = None) -> Dict[str, Any]:
        """Upload a file into MindsDB's `files` storage.

        Makes the file queryable under the `files` database (table name is the stem).
        """
        p = Path(path)
        target = table_name or p.stem
        url = f"{self.base_url}/files/{target}"
        data = {"original_file_name": p.name}
        with p.open("rb") as f:
            files = {"file": (p.name, f, "application/octet-stream")}
            resp = self.client.put(url, headers=self._headers(), data=data, files=files)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self.client.close()

    def sql(self, query: str) -> Dict[str, Any]:
        """Execute a SQL query via REST API.

        Example: SELECT * FROM files.my_table LIMIT 5
        """
        url = f"{self.base_url}/sql/query"
        payload = {"query": query}
        resp = self.client.post(url, headers={**self._headers(), "Content-Type": "application/json"}, json=payload)
        resp.raise_for_status()
        return resp.json()
