from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

from sentence_transformers import SentenceTransformer

from ...core.config import settings


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    normalize: bool
    batch_size: int


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> SentenceTransformer:  # pragma: no cover - heavy dependency
    return SentenceTransformer(model_name, device="cpu")


class EmbeddingBackend:
    """Thin wrapper around SentenceTransformer with cached model loading."""

    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or EmbeddingConfig(
            model_name=settings.rag_embedding_model,
            normalize=settings.rag_distance == "cosine",
            batch_size=max(1, settings.rag_embedding_batch_size),
        )

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _load_model(self.config.model_name)
        vectors = model.encode(
            list(texts),
            batch_size=max(1, self.config.batch_size),
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def encode_one(self, text: str) -> list[float]:
        results = self.encode([text])
        return results[0] if results else []
