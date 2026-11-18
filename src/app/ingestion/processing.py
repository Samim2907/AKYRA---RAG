from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable


def normalize(text: str) -> str:
    # Preserve line breaks so citations can identify their original extracted line range.
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[\t \f\v]+", " ", text)).strip()


def clean_and_dedupe(documents: Iterable[dict]) -> list[dict]:
    seen, result = set(), []
    for document in documents:
        text = normalize(document["text"])
        fingerprint = hashlib.sha256(text.encode()).hexdigest()
        if len(text) >= 50 and fingerprint not in seen:
            seen.add(fingerprint)
            result.append({**document, "title": normalize(document["title"]), "text": text})
    return result


def chunk_documents(documents: Iterable[dict], size: int, overlap: int) -> list[dict]:
    if overlap >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    chunks: list[dict] = []
    for document in documents:
        text, start, ordinal = document["text"], 0, 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                breakpoint = text.rfind(" ", start, end)
                if breakpoint > start + size // 2:
                    end = breakpoint
            content = text[start:end].strip()
            if content:
                leading_trim = len(text[start:end]) - len(text[start:end].lstrip())
                content_start = start + leading_trim
                chunk = {"id": f"{hashlib.sha1((document['url'] + str(document.get('page', ''))).encode()).hexdigest()[:12]}-{ordinal}", "text": content, "source_url": document["url"], "title": document["title"], "ordinal": ordinal, "line_start": text.count("\n", 0, content_start) + 1, "line_end": text.count("\n", 0, end) + 1}
                if document.get("page") is not None:
                    chunk["page"] = document["page"]
                chunks.append(chunk)
                ordinal += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks
