"""Retrieval layer.

Functional today: lexical search (ripgrep + Python fallback).
Scaffolded for later: embeddings/vector retrieval, reranking, hybrid fusion.
"""

from .base import (
    EmbeddingRetriever,
    HybridRetriever,
    LexicalRetriever,
    Reranker,
)
from .lexical import ripgrep_available, search

__all__ = [
    "search",
    "ripgrep_available",
    "LexicalRetriever",
    "EmbeddingRetriever",
    "Reranker",
    "HybridRetriever",
]
