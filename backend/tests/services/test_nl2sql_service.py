import pytest

from insight_backend.services.nl2sql_service import _ensure_required_prefix
from insight_backend.services.nl2sql_service import NL2SQLService


class _StubLLMClient:
    def __init__(self) -> None:
        self.last_messages = None

    def chat_completions(self, *, model: str, messages: list[dict[str, str]], temperature: int = 0) -> dict[str, object]:
        self.last_messages = messages
        return {"choices": [{"message": {"content": "stub response"}}]}


def test_ensure_required_prefix_accepts_cte_reference() -> None:
    sql = (
        "WITH recent AS (\n"
        "    SELECT id FROM files.tickets LIMIT 5\n"
        ")\n"
        "SELECT recent.id, u.id\n"
        "FROM recent\n"
        "JOIN files.users AS u ON u.id = recent.id\n"
        "LIMIT 5"
    )

    _ensure_required_prefix(sql)


def test_ensure_required_prefix_rejects_unprefixed_table() -> None:
    sql = "SELECT id FROM tickets LIMIT 5"

    with pytest.raises(RuntimeError):
        _ensure_required_prefix(sql)


def test_write_injects_retrieval_context(monkeypatch: pytest.MonkeyPatch) -> None:
    service = NL2SQLService()
    client = _StubLLMClient()
    monkeypatch.setattr(service, "_client_and_model", lambda: (client, "stub-model"))

    payload = [{"table": "tickets", "score": 0.92, "focus": "Portail KO", "values": {"description": "Portail KO"}}]
    result = service.write(
        question="Pourquoi le portail tombe ?",
        evidence=[{"sql": "SELECT 1", "rows": []}],
        retrieval_context=payload,
    )

    assert result == "stub response"
    assert client.last_messages is not None
    system_prompt = client.last_messages[0]["content"]
    assert "De la donnée à l'action" in system_prompt
    user_payload = client.last_messages[1]["content"]
    assert "retrieval_context" in user_payload
