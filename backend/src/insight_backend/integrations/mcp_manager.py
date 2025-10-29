from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse

from ..core.config import settings


log = logging.getLogger("insight.integrations.mcp")
BACKEND_ROOT = Path(__file__).resolve().parents[3]


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
                return [self._build_spec(it) for it in data]
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
                    return [self._build_spec(it) for it in data]
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

    def _build_spec(self, item: Dict[str, Any]) -> MCPServerSpec:
        normalized = self._normalize_item(item)
        normalized["env"] = self._resolve_env(normalized["env"])
        return MCPServerSpec(**normalized)

    def _resolve_env(self, env: Dict[str, str]) -> Dict[str, str]:
        if not env:
            return {}

        resolved = dict(env)
        if "VIS_REQUEST_SERVER" in resolved:
            base_url = resolved["VIS_REQUEST_SERVER"]
            try:
                resolved["VIS_REQUEST_SERVER"] = _resolve_vis_request_server(base_url)
            except Exception as exc:  # pragma: no cover - configuration error path
                raise RuntimeError(
                    f"Unable to resolve VIS_REQUEST_SERVER '{base_url}' "
                    f"using vis-ssr env '{settings.vis_ssr_env_path}'"
                ) from exc
        return resolved

    def list_servers(self) -> List[MCPServerSpec]:
        return list(self._servers)


def _resolve_vis_request_server(base_url: str) -> str:
    port = _load_vis_ssr_port(settings.vis_ssr_env_path)
    return _inject_port(base_url, port)


@lru_cache(maxsize=4)
def _load_vis_ssr_port(env_path: str) -> int:
    path = _resolve_path(env_path)
    if not path.exists():
        raise FileNotFoundError(f"vis-ssr env file not found: {path}")

    port_value: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != "GPT_VIS_SSR_PORT":
                continue
            candidate = value.strip()
            if (
                len(candidate) >= 2
                and candidate[0] == candidate[-1]
                and candidate[0] in {"'", '"'}
            ):
                candidate = candidate[1:-1]
            port_value = candidate.strip()
            break

    if port_value is None:
        raise ValueError(f"Missing GPT_VIS_SSR_PORT in '{path}'")

    try:
        port = int(port_value)
    except ValueError as exc:
        raise ValueError(f"Invalid GPT_VIS_SSR_PORT '{port_value}' in '{path}'") from exc

    if not (1 <= port <= 65535):
        raise ValueError(f"GPT_VIS_SSR_PORT '{port}' out of range (1-65535)")

    return port


def _inject_port(base_url: str, port: int) -> str:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid VIS_REQUEST_SERVER base URL '{base_url}'")

    username = parsed.username or ""
    password = parsed.password or ""

    auth = ""
    if username:
        auth = username
        if password:
            auth += f":{password}"
        auth += "@"

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError(f"Unable to determine host from '{base_url}'")

    host = hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    netloc = f"{auth}{host}:{port}"
    if parsed.port and parsed.port != port:
        log.debug(
            "Overriding VIS_REQUEST_SERVER port %s with %s for host %s",
            parsed.port,
            port,
            hostname,
        )

    return urlunparse(parsed._replace(netloc=netloc))


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    return path
