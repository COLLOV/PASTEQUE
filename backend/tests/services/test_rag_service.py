from pathlib import Path

from insight_backend.repositories.data_repository import DataRepository
from insight_backend.services.rag_service import TicketRAGService


class FakeEmbeddingClient:
    def embeddings(self, *, model: str, inputs):  # type: ignore[override]
        data = []
        for idx, text in enumerate(inputs):
            text_lower = text.casefold()
            base = 1.0
            vector = [
                base + (1.0 if "souris" in text_lower else 0.0),
                base + (1.0 if "lent" in text_lower else 0.0),
                base + len(text_lower) / 100.0,
            ]
            data.append({"index": idx, "embedding": vector})
        return {"data": data}


def write_tickets(path: Path) -> None:
    rows = [
        "ticket_id,resume,description,creation_date,departement\n",
        "JIRA-0105,Souris sans fil,L'appareil se déconnecte régulièrement,2025-04-21 11:22:18,Marketing\n",
        "JIRA-0309,Ordinateur lent,Le PC démarre en plus de 10 minutes,2025-04-21 11:22:18,Direction\n",
        "JIRA-0430,Imprimante,Impossible d'imprimer en recto-verso,2025-04-21 11:22:18,RH\n",
    ]
    path.write_text("".join(rows), encoding="utf-8")


def test_ticket_rag_returns_similar_tickets(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = data_dir / "tickets_jira.csv"
    write_tickets(csv_path)
    repo = DataRepository(tables_dir=data_dir)
    store_path = tmp_path / "vector_store" / "tickets_jira.json"
    service = TicketRAGService(
        repo=repo,
        client=FakeEmbeddingClient(),
        store_path=store_path,
        table_name="tickets_jira",
        text_columns=("resume", "description"),
        embedding_model="fake-model",
        batch_size=2,
    )

    first = service.retrieve("Ma souris ne répond plus", top_k=2)
    assert first.model == "fake-model"
    assert len(first.items) == 2
    assert first.items[0].ticket_id == "JIRA-0105"
    assert store_path.exists()

    second = service.retrieve("Mon ordinateur est très lent", top_k=1)
    assert second.items[0].ticket_id == "JIRA-0309"
