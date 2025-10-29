from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ..core.config import settings


log = logging.getLogger("insight.integrations.mcp")


@dataclass
class MCPServerSpec:
    name: str
    command: str
    args: List[str]
    env: Dict[str, str]


class MCPManager:
    """Gestionnaire minimal de configuration MCP.

    - Charge une liste de serveurs depuis `MCP_SERVERS_JSON` ou `MCP_CONFIG_PATH`.
    - Ne lance pas de processus automatiquement (évite les effets de bord en prod).
    - Vise à rendre la connexion simple côté moteur de chat (outil‑calling à venir).
    """

    def __init__(self) -> None:
        self._servers: List[MCPServerSpec] = self._load_servers()

    def _load_servers(self) -> List[MCPServerSpec]:
        # Priority: env JSON > file path
        raw = settings.mcp_servers_json
        if raw:
            try:
                data = json.loads(raw)
                return [MCPServerSpec(**self._normalize_item(it)) for it in data]
            except Exception as e:  # pragma: no cover - config error
                log.error("Invalid MCP_SERVERS_JSON: %s", e)
                return []

        if settings.mcp_config_path:
            path = Path(settings.mcp_config_path)
            if path.exists():
                try:
                    if path.suffix.lower() in {".yaml", ".yml"}:
                        import yaml  # optional
                        data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    else:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    return [MCPServerSpec(**self._normalize_item(it)) for it in data]
                except Exception as e:  # pragma: no cover - config error
                    log.error("Invalid MCP config file '%s': %s", path, e)
            else:
                log.warning("MCP config path not found: %s", path)
        return []

    @staticmethod
    def _normalize_item(it: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": it.get("name"),
            "command": it.get("command"),
            "args": list(it.get("args", []) or []),
            "env": dict(it.get("env", {}) or {}),
        }

    def list_servers(self) -> List[MCPServerSpec]:
        return list(self._servers)
