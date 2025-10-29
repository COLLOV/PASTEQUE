from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                data = self._apply_dynamic_env(data)
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
                        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
                        data = self._apply_dynamic_env(data, source_path=path, serializer="yaml", yaml_module=yaml)
                    else:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        data = self._apply_dynamic_env(data, source_path=path, serializer="json")
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

    def _apply_dynamic_env(
        self,
        data: Any,
        *,
        source_path: Optional[Path] = None,
        serializer: str | None = None,
        yaml_module: Any | None = None,
    ) -> Any:
        if not isinstance(data, list) or not data:
            return data

        port = self._read_vis_ssr_port()
        if port is None:
            return data

        url = f"http://localhost:{port}/"
        mutated = False
        for item in data:
            if not isinstance(item, dict):
                continue
            env = item.get("env")
            if isinstance(env, dict) and env.get("VIS_REQUEST_SERVER") != url:
                env["VIS_REQUEST_SERVER"] = url
                mutated = True

        if mutated and source_path:
            try:
                self._write_config(source_path, data, serializer=serializer, yaml_module=yaml_module)
            except Exception as exc:  # pragma: no cover - IO error
                log.error("Failed to update MCP config '%s': %s", source_path, exc)
        return data

    def _read_vis_ssr_port(self) -> Optional[int]:
        raw = os.getenv("GPT_VIS_SSR_PORT")
        if raw:
            return self._validate_port(raw.strip())

        path = self._vis_ssr_env_path()
        if not path or not path.exists():
            return None

        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                if key.strip() != "GPT_VIS_SSR_PORT":
                    continue
                return self._validate_port(value.strip().strip('"').strip("'"))
        except Exception as exc:  # pragma: no cover - IO error
            log.error("Failed to read SSR env file '%s': %s", path, exc)
        return None

    @staticmethod
    def _validate_port(value: str) -> Optional[int]:
        if not value.isdigit():
            log.error("Invalid GPT_VIS_SSR_PORT '%s' (must be numeric)", value)
            return None
        port = int(value, 10)
        if not (1 <= port <= 65535):
            log.error("Invalid GPT_VIS_SSR_PORT '%s' (must be in range 1-65535)", value)
            return None
        return port

    @staticmethod
    def _vis_ssr_env_path() -> Optional[Path]:
        try:
            root = Path(__file__).resolve().parents[4]
        except IndexError:  # pragma: no cover - unexpected layout
            log.error("Unable to resolve project root from %s", __file__)
            return None
        return root / "vis-ssr" / ".env"

    @staticmethod
    def _write_config(
        path: Path,
        data: Any,
        *,
        serializer: str | None,
        yaml_module: Any | None = None,
    ) -> None:
        if serializer == "yaml":
            if yaml_module is None:  # pragma: no cover - defensive
                raise RuntimeError("yaml module is required to serialize YAML config")
            dumped = yaml_module.safe_dump(data, sort_keys=False)
            path.write_text(dumped, encoding="utf-8")
        else:
            dumped = json.dumps(data, indent=2)
            path.write_text(f"{dumped}\n", encoding="utf-8")
