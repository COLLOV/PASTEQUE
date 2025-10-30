from typing import Any, Dict

from insight_backend.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from insight_backend.services.chat_service import ChatService
from insight_backend.services.rag_service import TicketRAGItem, TicketRAGResult


class DummyEngine:
    def __init__(self):
        self.last_payload: ChatRequest | None = None

    def run(self, payload: ChatRequest) -> ChatResponse:  # type: ignore[override]
        self.last_payload = payload
        return ChatResponse(reply="ok", metadata={"provider": "dummy"})


class StubRAGService:
    def __init__(self):
        self.calls: list[Dict[str, Any]] = []

    def retrieve(self, question: str, top_k: int) -> TicketRAGResult:
        self.calls.append({"question": question, "top_k": top_k})
        item = TicketRAGItem(
            ticket_id="T-1",
            resume="Souris bloquée",
            description="Le clic droit ne répond plus",
            departement="Support",
            creation_date="2025-04-21",
            score=0.95,
        )
        return TicketRAGResult(items=[item], model="stub-emb", top_k=top_k)


def test_chat_service_injects_rag(monkeypatch):
    engine = DummyEngine()
    service = ChatService(engine)
    stub = StubRAGService()

    monkeypatch.setattr(ChatService, "_ensure_ticket_rag", lambda self: stub)
    monkeypatch.setattr(ChatService, "_should_use_rag", lambda self, payload: (True, 2))

    payload = ChatRequest(messages=[ChatMessage(role="user", content="Problème de souris")])

    response = service.completion(payload)

    assert stub.calls
    assert stub.calls[0]["top_k"] == 2
    assert engine.last_payload is not None
    assert engine.last_payload.messages[-2].role == "system"
    assert "Contexte tickets" in engine.last_payload.messages[-2].content
    assert response.metadata and response.metadata.get("rag", {}).get("tickets")
    assert response.metadata["rag"]["tickets"][0]["ticket_id"] == "T-1"


def test_chat_service_should_use_rag_metadata(monkeypatch):
    engine = DummyEngine()
    service = ChatService(engine)

    from insight_backend.core.config import settings

    monkeypatch.setattr(settings, "rag_enabled", True)
    monkeypatch.setattr(settings, "rag_top_k", 3)

    payload = ChatRequest(
        messages=[ChatMessage(role="user", content="Bonjour")],
        metadata={"rag": {"top_k": 5}},
    )

    use_rag, top_k = service._should_use_rag(payload)
    assert use_rag is True
    assert top_k == 5

    payload.metadata = {"rag": {"enabled": False}}
    use_rag, top_k = service._should_use_rag(payload)
    assert use_rag is False
