import os
import subprocess
import sys
from pathlib import Path

from insight_backend.integrations.mcp_manager import MCPServerSpec
from insight_backend.services.mcp_chart_service import wrap_mcp_stdio_spec
import insight_backend.services.mcp_stdio_filter as filter_module


def test_wrap_mcp_stdio_spec_injects_filter_wrapper():
    spec = MCPServerSpec(
        name="gpt-vis-mcp",
        command="docker",
        args=["run", "image"],
        env={"EXISTING": "1"},
    )

    wrapped = wrap_mcp_stdio_spec(spec)

    assert wrapped.command == sys.executable or wrapped.command == "python3"
    assert wrapped.args[0] == str(Path(filter_module.__file__).resolve())
    assert wrapped.args[1] == "--"
    assert wrapped.args[2:] == ["docker", "run", "image"]

    assert wrapped.env["EXISTING"] == "1"
    assert wrapped.env["MCP_STDOUT_SUPPRESS_PREFIXES"].startswith("Saving chart to")
    assert wrapped.env["MCP_STDOUT_FILTER_LABEL"] == "gpt-vis-mcp"
    assert wrapped.env["PYTHONUNBUFFERED"] == "1"


def test_stdio_filter_redirects_non_json_lines(tmp_path):
    wrapper_path = Path(filter_module.__file__).resolve()
    payload = (
        'import sys\n'
        'print("Saving chart to: foo.png")\n'
        'print("{\\"jsonrpc\\":\\"2.0\\"}")\n'
    )

    env = os.environ.copy()
    env.pop("MCP_STDOUT_SUPPRESS_PREFIXES", None)
    env.pop("MCP_STDOUT_JSON_PREFIXES", None)

    result = subprocess.run(
        [
            sys.executable,
            str(wrapper_path),
            "--",
            sys.executable,
            "-c",
            payload,
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == '{"jsonrpc":"2.0"}'
    assert "Saving chart to: foo.png" in result.stderr
    assert "[mcp-filter" in result.stderr
