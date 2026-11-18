from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from .config import settings
from .ingestion.files import extract_documents
from .models import HealthResponse, IndexedSource, IndexSourcesResponse, IngestRequest, IngestResponse, QueryRequest, QueryResponse
from .services.guardrails import GuardrailError
from .services.rag import RAGService

app = FastAPI(title="Hybrid Web RAG", version="0.1.0", description="Crawl, index, and query a website with hybrid RAG.")
service = RAGService(settings)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", indexed_chunks=service.store.count)


@app.get("/v1/index/sources", response_model=IndexSourcesResponse)
async def index_sources() -> IndexSourcesResponse:
    return IndexSourcesResponse(sources=[IndexedSource(**source) for source in service.list_sources()], indexed_chunks=service.store.count)


@app.delete("/v1/index", status_code=204)
async def clear_index() -> Response:
    await service.clear_index()
    return Response(status_code=204)


@app.post("/v1/ingestions", response_model=IngestResponse, status_code=201)
async def create_ingestion(request: IngestRequest) -> IngestResponse:
    try:
        return await service.ingest(request.url, request.max_pages)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/documents", response_model=IngestResponse, status_code=201)
async def upload_documents(files: list[UploadFile] = File(...)) -> IngestResponse:
    if len(files) > 20:
        raise HTTPException(status_code=422, detail="Upload at most 20 files at a time.")
    documents = []
    try:
        for file in files:
            name = file.filename or "uploaded-file"
            content = await file.read()
            if len(content) > 25 * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"{name} exceeds the 25 MB limit.")
            documents.extend(extract_documents(name, content))
        return await service.ingest_documents(documents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        return await service.query(request.question, request.top_k)
    except GuardrailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/query/stream")
async def stream_query(question: str = Query(min_length=3, max_length=2000), top_k: int = Query(default=5, ge=1, le=10)) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        try:
            response = await service.query(question, top_k)
            # SSE event keeps clients responsive; switch AnswerGenerator to a streaming provider for token-level output.
            yield f"event: answer\ndata: {json.dumps(response.model_dump())}\n\n"
        except GuardrailError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
