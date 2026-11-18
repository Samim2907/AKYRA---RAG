from __future__ import annotations

import re
from collections import defaultdict


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def reciprocal_rank_fusion(*rankings: list[int], k: int = 60) -> list[int]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            scores[index] += 1 / (k + rank)
    return [index for index, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


class Reranker:
    """Cross-encoder when available; lexical fallback keeps local/offline operation possible."""

    def __init__(self) -> None:
        self._model = None
        self._failed = False

    def rank(self, query: str, candidates: list[tuple[int, dict]]) -> list[tuple[int, dict, float]]:
        if not candidates:
            return []
        try:
            if self._model is None and not self._failed:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            if self._model:
                scores = self._model.predict([(query, item["text"]) for _, item in candidates])
                return sorted([(idx, item, float(score)) for (idx, item), score in zip(candidates, scores)], key=lambda x: x[2], reverse=True)
        except Exception:
            self._failed = True
        terms = set(tokenize(query))
        return sorted([(idx, item, len(terms & set(tokenize(item["text"]))) / max(len(terms), 1)) for idx, item in candidates], key=lambda x: x[2], reverse=True)
