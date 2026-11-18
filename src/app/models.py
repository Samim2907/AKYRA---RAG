from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class IngestRequest(BaseModel):
    url: str = Field(min_length=3, max_length=2048)
    max_pages: int = Field(default=10, ge=1, le=100)

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, value: object) -> str:
        url = str(value).strip()
        if "://" not in url:
            url = f"https://{url}"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Enter a valid website hostname or an http(s) URL.")
        return url


class IngestResponse(BaseModel):
    status: Literal["completed"]
    pages_crawled: int
    documents_indexed: int
    chunks_indexed: int
    skipped_urls: list[str]
    completed_at: datetime


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class Citation(BaseModel):
    source_url: str
    title: str
    excerpt: str
    score: float
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieval: dict[str, int]
    generation_mode: Literal["llm", "extractive"]
    generation_label: str
    answer_origin: Literal["collection", "web", "model"]


class HealthResponse(BaseModel):
    status: str
    indexed_chunks: int


class IndexedSource(BaseModel):
    id: str
    label: str
    kind: Literal["website", "document"]
    source_url: str
    indexed_at: datetime


class IndexSourcesResponse(BaseModel):
    sources: list[IndexedSource]
    indexed_chunks: int
