from __future__ import annotations

from insight_backend.services.mcp_chart_service import ChartGenerationService


def test_inject_docker_env_inserts_before_image():
    base_args = [
        "run",
        "--rm",
        "-v",
        "/tmp/gpt-vis-charts:/tmp/gpt-vis-charts",
        "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp",
    ]
    env_values = {
        "NODE_OPTIONS": "--require /tmp/gpt-vis-charts/mcp_console_stderr.cjs",
        "RENDERED_IMAGE_PATH": "/tmp/gpt-vis-charts",
    }

    updated = ChartGenerationService._inject_docker_env(base_args, env_values)

    assert updated[:7] == [
        "run",
        "--rm",
        "-v",
        "/tmp/gpt-vis-charts:/tmp/gpt-vis-charts",
        "--env",
        "NODE_OPTIONS=--require /tmp/gpt-vis-charts/mcp_console_stderr.cjs",
        "--env",
    ]
    assert updated[7] == "RENDERED_IMAGE_PATH=/tmp/gpt-vis-charts"
    assert "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp" in updated


def test_inject_docker_env_leaves_non_docker_args_untouched():
    base_args = ["run", "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp"]
    env_values = {"NODE_OPTIONS": "--require test"}

    updated = ChartGenerationService._inject_docker_env(base_args, env_values)
    assert updated[:3] == ["run", "--env", "NODE_OPTIONS=--require test"]
    assert updated[-1] == "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp"
