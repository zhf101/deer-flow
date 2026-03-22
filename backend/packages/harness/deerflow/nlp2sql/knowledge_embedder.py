from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from deerflow.nlp2sql.knowledge_config import KnowledgeConfig

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class DeterministicEmbedder:
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class OpenAIEmbedder:
    def __init__(self, model: str, dimensions: int | None = None) -> None:
        from langchain_openai import OpenAIEmbeddings

        kwargs: dict[str, object] = {"model": model}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions
        self._embeddings = OpenAIEmbeddings(**kwargs)

    def embed(self, text: str) -> list[float]:
        return [float(value) for value in self._embeddings.embed_query(text)]


def build_embedder_from_settings(
    *,
    provider: str,
    model: str,
    dimensions: int,
) -> Embedder:
    provider = provider.casefold()
    if provider == "deterministic":
        return DeterministicEmbedder(dimensions)
    if provider == "openai":
        return OpenAIEmbedder(
            model=model,
            dimensions=dimensions,
        )
    raise RuntimeError(
        f"Unsupported NLP2SQL embedding provider '{provider}'. "
        "Supported providers: deterministic, openai."
    )


def build_embedder(config: KnowledgeConfig) -> Embedder:
    return build_embedder_from_settings(
        provider=config.embedding_provider,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
    )
