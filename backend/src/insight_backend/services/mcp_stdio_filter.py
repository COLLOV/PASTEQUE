from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Iterable, Sequence


DEFAULT_SUPPRESS_PREFIXES: tuple[str, ...] = ("Saving chart to",)
DEFAULT_JSON_PREFIXES: tuple[str, ...] = ("{", "[")


def _load_prefix_chars() -> tuple[str, ...]:
    raw = os.environ.get("MCP_STDOUT_JSON_PREFIXES")
    if not raw:
        return DEFAULT_JSON_PREFIXES
    chars = tuple(ch for ch in raw if not ch.isspace())
    return chars or DEFAULT_JSON_PREFIXES


def _load_suppress_prefixes() -> tuple[str, ...]:
    raw = os.environ.get("MCP_STDOUT_SUPPRESS_PREFIXES")
    if not raw:
        return DEFAULT_SUPPRESS_PREFIXES

    tokens: list[str] = []
    for segment in raw.replace("\r", "\n").split("\n"):
        for piece in segment.split("|"):
            stripped = piece.strip()
            if stripped:
                tokens.append(stripped)
    return tuple(tokens) or DEFAULT_SUPPRESS_PREFIXES


JSON_PREFIX_CHARS = _load_prefix_chars()
SUPPRESS_PREFIXES = _load_suppress_prefixes()
FILTER_LABEL = os.environ.get("MCP_STDOUT_FILTER_LABEL")


def _is_json_payload(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return False
    return stripped[0] in JSON_PREFIX_CHARS


def _is_suppressed(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(stripped.startswith(prefix) for prefix in SUPPRESS_PREFIXES)


def _relay_stdout_line(line: str) -> None:
    if _is_json_payload(line):
        sys.stdout.write(line)
        sys.stdout.flush()
        return

    if _is_suppressed(line):
        message = line.strip()
        if message:
            prefix = f"[mcp-filter:{FILTER_LABEL}] " if FILTER_LABEL else "[mcp-filter] "
            sys.stderr.write(f"{prefix}{message}\n")
            sys.stderr.flush()
        return

    sys.stderr.write(line)
    sys.stderr.flush()


def _pump_stdout(stream: Iterable[str]) -> None:
    try:
        for line in stream:
            _relay_stdout_line(line)
    finally:
        try:
            stream.close()  # type: ignore[attr-defined]
        except Exception:
            pass


def _pump_stderr(stream: Iterable[str]) -> None:
    try:
        for line in stream:
            sys.stderr.write(line)
            sys.stderr.flush()
    finally:
        try:
            stream.close()  # type: ignore[attr-defined]
        except Exception:
            pass


def _parse_command(argv: Sequence[str]) -> Sequence[str]:
    args = list(argv)
    if args and args[0] == "--":
        args = args[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_command(argv if argv is not None else sys.argv[1:])
    if not args:
        sys.stderr.write(
            "mcp_stdio_filter: missing command to execute. Use `... mcp_stdio_filter.py -- <cmd> [args...]`.\n"
        )
        return 2

    try:
        process = subprocess.Popen(  # noqa: S603 - intentional command execution
            args,
            stdin=sys.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        sys.stderr.write(f"mcp_stdio_filter: executable not found: {args[0]!r} ({exc})\n")
        return 127
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"mcp_stdio_filter: failed to spawn command {args!r}: {exc}\n")
        return 1

    stdout = process.stdout
    stderr = process.stderr
    if stdout is None or stderr is None:  # pragma: no cover - defensive
        process.kill()
        return 1

    stdout_thread = threading.Thread(target=_pump_stdout, args=(stdout,), daemon=True)
    stderr_thread = threading.Thread(target=_pump_stderr, args=(stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    return returncode


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
