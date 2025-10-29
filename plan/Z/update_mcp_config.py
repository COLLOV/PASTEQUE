from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    env_path = root / "vis-ssr" / ".env"
    config_path = root / "plan" / "Z" / "mcp.config.json"

    port = read_port(env_path)
    url = f"http://localhost:{port}/"

    data = load_config(config_path)
    mutated = False
    for item in data:
        env = item.get("env")
        if isinstance(env, dict) and env.get("VIS_REQUEST_SERVER") != url:
            env["VIS_REQUEST_SERVER"] = url
            mutated = True

    if mutated:
        config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_port(path: Path) -> int:
    if not path.exists():
        raise SystemExit(f"vis-ssr/.env not found at {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "GPT_VIS_SSR_PORT":
            continue
        return validate_port(value.strip().strip('"').strip("'"))

    raise SystemExit("GPT_VIS_SSR_PORT is not defined in vis-ssr/.env")


def validate_port(value: str) -> int:
    if not value.isdigit():
        raise SystemExit(f"Invalid GPT_VIS_SSR_PORT '{value}' (must be numeric)")
    port = int(value, 10)
    if not (1 <= port <= 65535):
        raise SystemExit(f"Invalid GPT_VIS_SSR_PORT '{value}' (must be between 1 and 65535)")
    return port


def load_config(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"MCP config file not found at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Unable to parse MCP config JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit("MCP config must be a JSON array")
    return data


if __name__ == "__main__":
    main()
