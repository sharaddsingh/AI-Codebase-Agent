"""Retrieval interfaces and the (deferred) hybrid-RAG scaffold.

Today retrieval is purely lexical (:mod:`retrieval.lexical`).  This module
documents the target architecture for the "Hybrid RAG" phase so the agent can
later be pointed at a richer retriever **without changing its call sites**:

    lexical search  ─┐
    vector search   ─┼─▶  fuse / dedupe  ─▶  rerank  ─▶  ranked snippets
    (symbol search) ─┘

The abstract classes below define that surface.  Their methods raise
:class:`NotSupportedError` — the shape is real, the implementation is not built.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from code_intelligence.errors import NotSupportedError
from code_intelligence.ignore import IgnoreRules
from code_intelligence.models import SearchResults


class LexicalRetriever:
    """Thin, functional adapter over :func:`retrieval.lexical.search`."""

    def search(
        self,
        root: Path,
        ignore: IgnoreRules,
        query: str,
        *,
        repo_id: str = "",
        **kwargs: object,
    ) -> SearchResults:
        from .lexical import search as _search

        return _search(root, ignore, query, repo_id=repo_id, **kwargs)  # type: ignore[arg-type]


class EmbeddingRetriever(ABC):
    """DEFERRED (Hybrid RAG phase): dense vector search over chunked code.

    Planned backing store: Qdrant.  Chunks are produced per snapshot so vectors
    can be invalidated/rebuilt when the snapshot id changes.
    """

    @abstractmethod
    def index(self, root: Path, snapshot_id: str) -> None: ...

    @abstractmethod
    def query(self, text: str, *, top_k: int = 20) -> SearchResults: ...


class Reranker(ABC):
    """DEFERRED (Hybrid RAG phase): cross-encoder reranking of fused candidates."""

    @abstractmethod
    def rerank(self, query: str, results: SearchResults, *, top_k: int = 10) -> SearchResults: ...


class HybridRetriever(ABC):
    """DEFERRED (Hybrid RAG phase): fuse lexical + vector, then rerank.

    This is the surface the agent will call instead of :func:`retrieval.lexical.search`
    once hybrid retrieval exists — same inputs (query + repo scope), richer ranking.
    """

    @abstractmethod
    def retrieve(
        self, root: Path, ignore: IgnoreRules, query: str, *, repo_id: str = "", top_k: int = 10
    ) -> SearchResults:
        """Return ranked snippets by fusing lexical + vector candidates and reranking."""
        ...

    def __init__(self) -> None:
        raise NotSupportedError(
            "HybridRetriever is deferred to the Hybrid RAG phase "
            "(lexical + embeddings/vector retrieval + reranking)."
        )
