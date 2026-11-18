from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .ranking import tokenize


class HybridStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.chunks: list[dict] = []
        self.bm25: BM25Okapi | None = None
        self.index = None
        self.embeddings: np.ndarray | None = None
        self.uses_hnsw = False
        self.dimension = 0

    @property
    def count(self) -> int:
        return len(self.chunks)

    def build(self, chunks: list[dict], embeddings: np.ndarray) -> None:
        if not chunks:
            raise ValueError("No usable content was found while crawling")
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings are misaligned")
        self.chunks, self.dimension = chunks, int(embeddings.shape[1])
        self.bm25 = BM25Okapi([tokenize(chunk["text"]) for chunk in chunks])
        self.embeddings = embeddings
        try:
            import hnswlib
            self.index = hnswlib.Index(space="cosine", dim=self.dimension)
            self.index.init_index(max_elements=len(chunks), ef_construction=200, M=16)
            self.index.add_items(embeddings, np.arange(len(chunks)))
            self.index.set_ef(max(50, min(200, len(chunks))))
            self.uses_hnsw = True
        except ImportError:
            self.index = None
            self.uses_hnsw = False

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "chunks.json").write_text(json.dumps(self.chunks, ensure_ascii=False), encoding="utf-8")
        (self.directory / "metadata.json").write_text(json.dumps({"dimension": self.dimension, "uses_hnsw": self.uses_hnsw}), encoding="utf-8")
        np.save(self.directory / "embeddings.npy", self.embeddings)
        if self.uses_hnsw:
            self.index.save_index(str(self.directory / "dense_hnsw.bin"))

    def load(self) -> bool:
        chunks_path, metadata_path, embeddings_path = (self.directory / "chunks.json", self.directory / "metadata.json", self.directory / "embeddings.npy")
        if not all(path.exists() for path in (chunks_path, metadata_path, embeddings_path)):
            return False
        self.chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.dimension = metadata["dimension"]
        self.embeddings = np.load(embeddings_path)
        self.bm25 = BM25Okapi([tokenize(chunk["text"]) for chunk in self.chunks])
        self.uses_hnsw = False
        index_path = self.directory / "dense_hnsw.bin"
        if metadata.get("uses_hnsw") and index_path.exists():
            try:
                import hnswlib
                self.index = hnswlib.Index(space="cosine", dim=self.dimension)
                self.index.load_index(str(index_path), max_elements=len(self.chunks))
                self.index.set_ef(max(50, min(200, len(self.chunks))))
                self.uses_hnsw = True
            except ImportError:
                self.index = None
        return True

    def dense_search(self, query_embedding: np.ndarray, limit: int) -> list[int]:
        if self.uses_hnsw and self.index:
            labels, _ = self.index.knn_query(query_embedding, k=min(limit, len(self.chunks)))
            return [int(label) for label in labels[0]]
        if self.embeddings is None:
            return []
        scores = self.embeddings @ query_embedding[0]
        return [int(index) for index in np.argsort(scores)[::-1][:limit]]

    def keyword_search(self, query: str, limit: int) -> list[int]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        return [int(index) for index in np.argsort(scores)[::-1][:limit] if scores[index] > 0]
