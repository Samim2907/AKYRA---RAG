from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..config import Settings
from ..ingestion.crawler import WebsiteCrawler
from ..ingestion.processing import chunk_documents, clean_and_dedupe
from ..models import Citation, IngestResponse, QueryResponse
from ..retrieval.embeddings import Embedder
from ..retrieval.ranking import Reranker, reciprocal_rank_fusion
from ..retrieval.store import HybridStore
from .answering import AnswerGenerator
from .guardrails import validate_answer, validate_question


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = HybridStore(settings.data_dir)
        self.store.load()
        self.sources: list[dict] = self._read_json("sources.json", [])
        if not self.sources:
            existing_documents = self._read_json("documents.json", [])
            unique_sources = {document["url"]: document for document in existing_documents}
            self.sources = [self._source_record("document" if url.startswith("upload://") else "website", document["title"] if url.startswith("upload://") else urlparse(url).netloc, url) for url, document in unique_sources.items()]
            if self.sources:
                settings.data_dir.mkdir(parents=True, exist_ok=True)
                (settings.data_dir / "sources.json").write_text(json.dumps(self.sources, ensure_ascii=False), encoding="utf-8")
        self.embedder = Embedder(settings.embedding_model)
        self.reranker = Reranker()
        self.generator = AnswerGenerator(settings.llm_provider, settings.openai_api_key, settings.openai_chat_model, settings.xai_api_key, settings.xai_model, settings.groq_api_key, settings.groq_model)
        self._ingest_lock = asyncio.Lock()

    async def ingest(self, url: str, max_pages: int) -> IngestResponse:
        async with self._ingest_lock:
            documents, skipped = await WebsiteCrawler(self.settings.request_timeout_seconds).crawl(url, min(max_pages, self.settings.max_crawl_pages))
            cleaned = clean_and_dedupe(documents)
            if not chunk_documents(cleaned, self.settings.chunk_size, self.settings.chunk_overlap):
                diagnostic = "; ".join(skipped[:3]) or "The page may be JavaScript-only or contain no extractable text."
                raise ValueError(f"No usable content was found while crawling. {diagnostic}")
            host = urlparse(url).netloc
            total_documents, total_chunks = await self._commit_documents(cleaned, [self._source_record("website", host, url)])
            return IngestResponse(status="completed", pages_crawled=len(documents), documents_indexed=total_documents, chunks_indexed=total_chunks, skipped_urls=skipped, completed_at=datetime.now(timezone.utc))

    async def ingest_documents(self, documents: list[dict]) -> IngestResponse:
        """Index uploaded, already-extracted documents using the same processing pipeline."""
        async with self._ingest_lock:
            cleaned = clean_and_dedupe(documents)
            if not chunk_documents(cleaned, self.settings.chunk_size, self.settings.chunk_overlap):
                raise ValueError("No extractable text was found in the uploaded files.")
            records = {document["url"]: self._source_record("document", document["title"], document["url"]) for document in cleaned}
            total_documents, total_chunks = await self._commit_documents(cleaned, list(records.values()))
            return IngestResponse(status="completed", pages_crawled=0, documents_indexed=total_documents, chunks_indexed=total_chunks, skipped_urls=[], completed_at=datetime.now(timezone.utc))

    def list_sources(self) -> list[dict]:
        return self.sources

    async def clear_index(self) -> None:
        async with self._ingest_lock:
            for name in ("chunks.json", "metadata.json", "embeddings.npy", "dense_hnsw.bin", "documents.json", "sources.json"):
                (self.settings.data_dir / name).unlink(missing_ok=True)
            self.store = HybridStore(self.settings.data_dir)
            self.sources = []

    async def _commit_documents(self, incoming: list[dict], source_records: list[dict]) -> tuple[int, int]:
        """Replace re-ingested sources, retain other sources, then rebuild both retrieval indexes."""
        existing = self._read_json("documents.json", [])
        incoming_urls = {document["url"] for document in incoming}
        combined = clean_and_dedupe([document for document in existing if document["url"] not in incoming_urls] + incoming)
        chunks = chunk_documents(combined, self.settings.chunk_size, self.settings.chunk_overlap)
        embeddings = await asyncio.to_thread(self.embedder.encode, [chunk["text"] for chunk in chunks])
        new_store = HybridStore(self.settings.data_dir)
        new_store.build(chunks, embeddings)
        await asyncio.to_thread(new_store.save)
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "documents.json").write_text(json.dumps(combined, ensure_ascii=False), encoding="utf-8")
        record_ids = {record["id"] for record in source_records}
        self.sources = [record for record in self.sources if record["id"] not in record_ids] + source_records
        (self.settings.data_dir / "sources.json").write_text(json.dumps(self.sources, ensure_ascii=False), encoding="utf-8")
        self.store = new_store
        return len(combined), len(chunks)

    def _source_record(self, kind: str, label: str, source_url: str) -> dict:
        identity = f"{kind}:{source_url}"
        return {"id": hashlib.sha1(identity.encode()).hexdigest()[:16], "label": label, "kind": kind, "source_url": source_url, "indexed_at": datetime.now(timezone.utc).isoformat()}

    def _read_json(self, filename: str, default: list) -> list:
        path = self.settings.data_dir / filename
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    async def query(self, question: str, top_k: int) -> QueryResponse:
        question = validate_question(question)
        if not self.store.count:
            answer, origin = await asyncio.to_thread(self.generator.answer, question, [], self.settings.enable_web_fallback)
            return QueryResponse(answer=answer, citations=[], retrieval={"dense": 0, "keyword": 0, "fused": 0, "reranked": 0}, generation_mode=self.generator.generation_mode, generation_label=f"{self.generator.provider.upper()} WEB SEARCH" if origin == "web" else self.generator.generation_label, answer_origin=origin)
        embedding = await asyncio.to_thread(self.embedder.encode, [question])
        dense = self.store.dense_search(embedding, self.settings.dense_candidates)
        keyword = self.store.keyword_search(question, self.settings.bm25_candidates)
        fused = reciprocal_rank_fusion(dense, keyword)
        reranked = await asyncio.to_thread(self.reranker.rank, question, [(index, self.store.chunks[index]) for index in fused[:max(self.settings.rerank_candidates, top_k)]])
        selected = reranked[:top_k]
        contexts = [item for _, item, _ in selected]
        # No BM25 match is a conservative signal that the collection likely has no material on the question.
        answer, origin = await asyncio.to_thread(self.generator.answer, question, contexts, self.settings.enable_web_fallback and not keyword)
        answer = validate_answer(answer, len(contexts))
        citations = [Citation(source_url=item["source_url"], title=item["title"], excerpt=item["text"][:300], score=round(score, 4), page=item.get("page"), line_start=item.get("line_start"), line_end=item.get("line_end")) for _, item, score in selected] if origin == "collection" else []
        label = f"{self.generator.provider.upper()} WEB SEARCH" if origin == "web" else self.generator.generation_label
        return QueryResponse(answer=answer, citations=citations, retrieval={"dense": len(dense), "keyword": len(keyword), "fused": len(fused), "reranked": len(reranked)}, generation_mode=self.generator.generation_mode, generation_label=label, answer_origin=origin)
