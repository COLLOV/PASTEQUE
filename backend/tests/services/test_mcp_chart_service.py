import pytest
from pydantic import ValidationError

from insight_backend.services.mcp_chart_service import ChartAgentOutput


def test_chart_agent_output_parses_json_string_chart_spec():
    output = ChartAgentOutput.model_validate(
        {
            "chart_url": "/tmp/chart.png",
            "tool_name": "generate_bar_chart",
            "chart_spec": '{"type": "bar", "x": "month"}',
        }
    )
    assert output.chart_spec == {"type": "bar", "x": "month"}


def test_chart_agent_output_rejects_non_object_chart_spec():
    with pytest.raises(ValidationError):
        ChartAgentOutput.model_validate(
            {
                "chart_url": "/tmp/chart.png",
                "tool_name": "generate_bar_chart",
                "chart_spec": '["invalid"]',
            }
        )
