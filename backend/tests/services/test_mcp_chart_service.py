from __future__ import annotations

from pathlib import Path

from insight_backend.services.mcp_chart_service import ChartGenerationService


def test_prepare_command_args_injects_env_before_image():
    base_args = [
        "run",
        "--rm",
        "-v",
        "/tmp/gpt-vis-charts:/tmp/gpt-vis-charts",
        "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp",
    ]
    env = {
        "NODE_OPTIONS": "--require /tmp/gpt-vis-charts/mcp_console_stderr.cjs",
        "RENDERED_IMAGE_PATH": "/tmp/gpt-vis-charts",
    }

    updated = ChartGenerationService._prepare_command_args("docker", base_args, env)

    assert updated is not base_args
    image_index = updated.index("ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp")
    assert updated[image_index - 4:image_index] == [
        "--env",
        "NODE_OPTIONS",
        "--env",
        "RENDERED_IMAGE_PATH",
    ]


def test_prepare_command_args_skips_existing_env():
    base_args = [
        "run",
        "--rm",
        "--env",
        "NODE_OPTIONS",
        "-v",
        "/tmp/gpt-vis-charts:/tmp/gpt-vis-charts",
        "ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp",
    ]
    env = {
        "NODE_OPTIONS": "--require /tmp/gpt-vis-charts/mcp_console_stderr.cjs",
        "RENDERED_IMAGE_PATH": "/tmp/gpt-vis-charts",
    }

    updated = ChartGenerationService._prepare_command_args("docker", base_args, env)

    image_index = updated.index("ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp")
    assert updated[image_index - 2:image_index] == [
        "--env",
        "RENDERED_IMAGE_PATH",
    ]


def test_prepare_command_args_noop_for_non_docker():
    base_args = ["node", "server.mjs"]
    env = {"NODE_OPTIONS": "--require script.cjs"}
    assert ChartGenerationService._prepare_command_args("node", base_args, env) == base_args


def test_ensure_console_patch_writes_once(tmp_path: Path):
    patch_source = tmp_path / "source.cjs"
    patch_source.write_text("console.log('patched');", encoding="utf-8")

    storage = tmp_path / "storage"
    storage.mkdir()

    target = ChartGenerationService._ensure_console_patch(storage, patch_source)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "console.log('patched');"

    # Modify target to ensure the helper refreshes it if content diverges.
    target.write_text("console.log('old');", encoding="utf-8")
    refreshed = ChartGenerationService._ensure_console_patch(storage, patch_source)
    assert refreshed.read_text(encoding="utf-8") == "console.log('patched');"
