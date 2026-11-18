from src.app.ingestion.processing import chunk_documents, clean_and_dedupe, normalize


def test_normalizes_and_deduplicates_documents() -> None:
    source = {"url": "https://example.test/a", "title": " A  title ", "text": "word  " * 20}
    duplicates = clean_and_dedupe([source, {**source, "url": "https://example.test/b"}])
    assert len(duplicates) == 1
    assert duplicates[0]["title"] == "A title"
    assert normalize("one\n\t two") == "one\n two"


def test_chunking_terminates_and_preserves_metadata() -> None:
    chunks = chunk_documents([{"url": "https://example.test", "title": "Example", "text": "x " * 100}], size=40, overlap=10)
    assert len(chunks) > 1
    assert chunks[-1]["source_url"] == "https://example.test"
    assert all(len(chunk["text"]) <= 40 for chunk in chunks)
