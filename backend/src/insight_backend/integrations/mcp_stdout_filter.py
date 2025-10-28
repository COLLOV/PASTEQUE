from __future__ import annotations

import json
import os
import subprocess
import sys
from threading import Thread
from typing import Iterable


def _stderr_forwarder(stream: Iterable[str]) -> None:
    for chunk in stream:
        sys.stderr.write(chunk)
        sys.stderr.flush()


def _is_json_line(payload: str) -> bool:
    stripped = payload.lstrip()
    if not stripped:
        return False
    if stripped[0] not in ("{", "["):
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _filter_stdout(stream: Iterable[str]) -> None:
    for line in stream:
        if _is_json_line(line):
            sys.stdout.write(line)
            sys.stdout.flush()
        else:
            sys.stderr.write(line)
            sys.stderr.flush()


def main(argv: list[str]) -> int:
    if "--" in argv:
        split_at = argv.index("--")
        target = argv[split_at + 1 :]
    else:
        target = argv[:]

    if not target:
        sys.stderr.write("mcp_stdout_filter: no command provided\n")
        sys.stderr.flush()
        return 2

    env = os.environ.copy()
    process = subprocess.Popen(
        target,
        stdin=sys.stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    assert process.stdout and process.stderr

    stderr_thread = Thread(target=_stderr_forwarder, args=(iter(process.stderr.readline, ""),), daemon=True)
    stderr_thread.start()

    _filter_stdout(iter(process.stdout.readline, ""))

    process.wait()
    stderr_thread.join()
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
