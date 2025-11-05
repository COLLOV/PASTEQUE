import pytest

from pydantic_ai import messages
from pydantic_ai.agent import AgentRunResult
from pydantic_ai._agent_graph import GraphAgentState

from insight_backend.services.mcp_chart_service import (
    ChartAgentOutput,
    ChartGenerationError,
    ChartGenerationService,
)


def _build_run_result(
    *,
    llm_url: str,
    tool_name: str,
    tool_return_content,
    include_dataset_tool: bool = True,
):
    history: list[messages.ModelMessage] = []

    history.append(
        messages.ModelRequest(parts=[messages.UserPromptPart("Show me sales")])
    )

    if include_dataset_tool:
        history.append(
            messages.ModelResponse(
                parts=[
                    messages.ToolCallPart(
                        "get_sql_result",
                        {"limit": 5},
                        tool_call_id="sql-1",
                    )
                ]
            )
        )
        history.append(
            messages.ModelRequest(
                parts=[
                    messages.ToolReturnPart(
                        tool_name="get_sql_result",
                        content={"columns": ["amount"], "rows": [{"amount": 10}]},
                        tool_call_id="sql-1",
                    )
                ]
            )
        )

    history.append(
        messages.ModelResponse(
            parts=[
                messages.ToolCallPart(
                    tool_name,
                    {"type": "bar"},
                    tool_call_id="chart-1",
                )
            ]
        )
    )
    history.append(
        messages.ModelRequest(
            parts=[
                messages.ToolReturnPart(
                    tool_name=tool_name,
                    content=tool_return_content,
                    tool_call_id="chart-1",
                )
            ]
        )
    )

    output = ChartAgentOutput(
        chart_url=llm_url,
        tool_name=tool_name,
        chart_title="",
        chart_description="",
        chart_spec={},
    )

    state = GraphAgentState(message_history=history)
    return AgentRunResult(output=output, _state=state)


def test_validate_agent_run_uses_mcp_url():
    expected_url = "http://localhost:6300/charts/chart.png"
    run_result = _build_run_result(
        llm_url=expected_url,
        tool_name="chart_generate",
        tool_return_content={"success": True, "url": expected_url},
    )

    service = ChartGenerationService.__new__(ChartGenerationService)
    assert service._validate_agent_run(run_result) == expected_url


def test_validate_agent_run_prefers_server_url(caplog):
    expected_url = "http://localhost:6300/charts/chart.png"
    run_result = _build_run_result(
        llm_url="https://fake.invalid/chart.png",
        tool_name="chart_generate",
        tool_return_content={"success": True, "url": expected_url},
    )

    service = ChartGenerationService.__new__(ChartGenerationService)
    with caplog.at_level("WARNING"):
        canonical_url = service._validate_agent_run(run_result)

    assert canonical_url == expected_url
    assert "URL de graphique discordante" in caplog.text


def test_validate_agent_run_requires_dataset_tool():
    expected_url = "http://localhost:6300/charts/chart.png"
    run_result = _build_run_result(
        llm_url=expected_url,
        tool_name="chart_generate",
        tool_return_content={"success": True, "url": expected_url},
        include_dataset_tool=False,
    )

    service = ChartGenerationService.__new__(ChartGenerationService)
    with pytest.raises(ChartGenerationError, match="get_sql_result"):
        service._validate_agent_run(run_result)


def test_validate_agent_run_rejects_missing_url():
    run_result = _build_run_result(
        llm_url="http://localhost:6300/charts/chart.png",
        tool_name="chart_generate",
        tool_return_content={"success": True},
    )

    service = ChartGenerationService.__new__(ChartGenerationService)
    with pytest.raises(ChartGenerationError, match="aucune URL"):
        service._validate_agent_run(run_result)
