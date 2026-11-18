# AKYRA — Hybrid Web and Document RAG

AKYRA is a FastAPI application that turns public websites and uploaded documents into a searchable knowledge collection. It provides a browser workspace for indexing and asking questions, plus a REST API for integrations.

## Features

`website/file → clean + deduplicate → chunk → embed → dense + BM25 indexes`

`question → guardrails → dense + BM25 retrieval → RRF → reranking → answer + citations`

- Crawls public, same-domain website pages while respecting `robots.txt`.
- Uses standard HTML extraction and a Playwright/Chromium fallback for JavaScript pages.
- Supports PDF, DOC/DOCX, ODT, RTF, PPTX, XLS/XLSX, CSV/TSV, EPUB, JSON, YAML, XML, HTML, Markdown, source code, logs, and UTF-8 text files.
- Uses dense semantic search plus BM25 keyword search, Reciprocal Rank Fusion, and reranking.
- Shows PDF citations with extracted page and line ranges.
- Maintains multiple indexed websites/files in one collection and can clear every record.
- Uses a configured LLM for generated answers and can fall back to live web search for questions unrelated to the collection.

## Requirements

- Python 3.11+
- Windows, macOS, or Linux
- Internet access for first-time model downloads and optional LLM/web search
- Optional API key for Groq, xAI/Grok, or OpenAI

## Project layout

```text
RAG/
├── app.py                     # FastAPI/Uvicorn entry point
├── src/app/
│   ├── main.py                # HTTP routes
│   ├── config.py              # Environment settings
│   ├── ingestion/             # Web crawling and file extraction
│   ├── retrieval/             # Embeddings, indexes, RRF, reranking
│   ├── services/              # Guardrails, answers, collection management
│   └── static/index.html      # AKYRA browser interface
├── data/                      # Generated indexes and records; do not commit
├── tests/
├── .env                       # Local secrets; do not commit
├── .env.example               # Safe configuration template
├── requirements.txt
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

## Setup on Windows

Open PowerShell in the project root and create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell prevents activation, allow it for this terminal only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

For development tools such as pytest and Ruff:

```powershell
pip install -e ".[dev]"
```

If your editor marks imports such as `fastapi` as unresolved, select `.venv` as its Python interpreter.

### JavaScript-heavy websites

Install Chromium once for Playwright:

```powershell
python -m playwright install chromium
```

AKYRA uses it only when ordinary HTML extraction is empty or looks like a challenge page.

## Configure `.env`

Never add secrets to `.env.example`. Put actual keys only in `.env`.

### Groq

Use this if your key starts with `gsk_`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
GROQ_MODEL=openai/gpt-oss-20b
ENABLE_WEB_FALLBACK=true
```

Groq is not xAI/Grok. A `gsk_...` credential belongs in `GROQ_API_KEY`, not `XAI_API_KEY`.

### xAI / Grok

```env
LLM_PROVIDER=grok
XAI_API_KEY=your_xai_key
XAI_MODEL=grok-4.7
ENABLE_WEB_FALLBACK=true
```

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_CHAT_MODEL=gpt-4.1-mini
ENABLE_WEB_FALLBACK=true
```

Without a configured provider, AKYRA remains usable but returns an **extractive fallback**—relevant complete sentences selected from the indexed collection rather than a synthesized answer.

### Index tuning settings

```env
RAG_DATA_DIR=./data
RAG_CHUNK_SIZE=900
RAG_CHUNK_OVERLAP=150
RAG_DENSE_CANDIDATES=20
RAG_BM25_CANDIDATES=20
RAG_RERANK_CANDIDATES=10
RAG_MAX_CRAWL_PAGES=25
RAG_REQUEST_TIMEOUT_SECONDS=20
```

## Run with Uvicorn

`uvicorn` is the ASGI server that hosts FastAPI locally. It is spelled **Uvicorn**, not “Unicorn”.

Development mode reloads automatically whenever source files change:

```powershell
uvicorn app:app --reload
```

Open these URLs:

- Browser workspace: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Interactive API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

Stop the server with `Ctrl+C`.

For a production-style local run without automatic reload:

```powershell
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Using the browser workspace

### Index a website

1. Enter a public hostname or URL, such as `docs.python.org/3/`.
2. Choose crawl depth; start with 3–5 pages for a demo.
3. Click **Index website**.
4. Wait for the completion message and check **Indexed sources**.
5. Ask questions in **Ask the collection**.

HTTPS is added automatically if omitted. The crawler stays on the same host, honors `robots.txt`, and does not bypass login pages, access controls, or website restrictions.

### Upload files

1. Click **Choose files**.
2. Choose up to 20 supported files, 25 MB each.
3. Click **Upload & index**.
4. Ask questions after indexing completes.

PDF page/line values refer to extracted text. Image-only or scanned PDFs need OCR before upload.

### Manage sources and reset data

The **Indexed sources** panel lists each indexed website/file and the total passage count.

- New sources are added to the existing collection.
- Re-uploading the same filename replaces its previous indexed copy.
- **Clear all records** removes all documents, chunks, embeddings, dense-index files, BM25 state, and source records from `data/`.

## Answer modes

| Label | Meaning |
|---|---|
| `SOURCE TRACE` | Answer is grounded in indexed content and has document citations. |
| `GROQ WEB SEARCH` | No collection keyword match; live Groq browser search answered the question. |
| `MODEL KNOWLEDGE` | No collection keyword match and web search was unavailable; configured LLM used general knowledge. |
| `EXTRACTIVE FALLBACK` | No LLM is configured; passages from the collection were selected directly. |

External/model-knowledge answers are not document-grounded. Verify them before using them for legal, medical, financial, safety, or time-sensitive decisions.

## REST API

### Add a website

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/ingestions `
  -ContentType 'application/json' `
  -Body '{"url":"https://docs.python.org/3/","max_pages":5}'
```

### Upload documents

Use `POST /v1/documents` with multipart form fields named `files`. The easiest way to try it is the interactive form at `/docs`.

### Ask a question

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/v1/query `
  -ContentType 'application/json' `
  -Body '{"question":"What is this documentation about?","top_k":5}'
```

### List or clear indexed sources

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/index/sources
Invoke-WebRequest -Method Delete http://127.0.0.1:8000/v1/index
```

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | AKYRA browser workspace |
| `GET` | `/health` | Service health and indexed chunk count |
| `POST` | `/v1/ingestions` | Crawl and add a website |
| `POST` | `/v1/documents` | Upload and add documents |
| `POST` | `/v1/query` | Query collection or external fallback |
| `GET` | `/v1/query/stream` | Server-Sent Events query response |
| `GET` | `/v1/index/sources` | List indexed sources |
| `DELETE` | `/v1/index` | Clear all indexed data |

## Test the project

```powershell
pytest -q
```

## Docker deployment

Ensure `.env` is configured, then run:

```powershell
docker compose up --build
```

Open `http://127.0.0.1:8000`. The persistent Docker volume `rag-data` keeps indexes across container restarts.

For public deployment, use HTTPS, authentication, rate limiting, a reverse proxy, and persistent managed storage. Do not expose an unauthenticated ingestion endpoint directly to the internet.

## Troubleshooting

### Missing imports or `ModuleNotFoundError`

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### `hnswlib` fails on Windows

HNSW is optional. AKYRA automatically falls back to exact cosine dense search. To enable HNSW later, install Microsoft C++ Build Tools and run:

```powershell
pip install -e ".[hnsw]"
```

### A website has no usable text

The site may block crawlers, disallow its path in `robots.txt`, need JavaScript, require authentication, or return a challenge page. Install Playwright Chromium, lower crawl depth, and try a public text-heavy page. AKYRA does not bypass access controls.

### `EXTRACTIVE FALLBACK` appears

No valid provider key was loaded. Confirm values are in `.env`, not `.env.example`, then stop and restart Uvicorn.

### Groq errors

Confirm `LLM_PROVIDER=groq`, set your `gsk_...` credential as `GROQ_API_KEY`, and verify that the selected model is enabled for your account.

## Security and responsible use

- Keep `.env` private; never commit or screenshot API keys.
- Rotate any credential exposed in chat, screenshots, Git history, or logs.
- Respect `robots.txt`, site terms, rate limits, and copyright.
- Do not index private or sensitive information without authorization.
