"""Local e5 embedding client. Loaded lazily (never at startup) and shared process-wide."""

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def resolve_device(preference: str = "auto") -> str:
    if preference in ("cpu", "cuda"):
        return preference
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:  # pragma: no cover
        return "cpu"


class EmbeddingClient:
    """Wraps sentence-transformers with the e5 'query: ' / 'passage: ' convention."""

    def __init__(self, model_name: str, device: str = "auto") -> None:
        self.model_name = model_name
        self.device_preference = device
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str | None:
        return str(self._model.device) if self._model is not None else None

    def _load(self) -> "SentenceTransformer":
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                device = resolve_device(self.device_preference)
                logger.info("loading embedding model", extra={"data": {"model": self.model_name, "device": device}})
                self._model = SentenceTransformer(self.model_name, device=device)
            return self._model

    def dimension(self) -> int:
        dim = self._load().get_sentence_embedding_dimension()
        assert dim is not None
        return int(dim)

    def _encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 200,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"], batch_size=1)[0].tolist()

    def embed_passages(self, texts: list[str], batch_size: int | None = None) -> np.ndarray:
        if batch_size is None:
            # e5-base fits comfortably at 32 on a 4–6 GB laptop GPU; be gentler on CPU RAM.
            batch_size = 32 if resolve_device(self.device_preference) == "cuda" else 16
        return self._encode([f"passage: {t}" for t in texts], batch_size=batch_size)

    def unload(self) -> None:
        """Free GPU memory (e.g. before loading an OCR model)."""
        with self._lock:
            self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:  # pragma: no cover
            pass


_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient(settings.embedding_model, settings.embedding_device)
    return _client
