from __future__ import annotations

import csv
import io
import json
import subprocess
import tempfile
import xml.etree.ElementTree as element_tree
from pathlib import Path

import ebooklib
import yaml
from bs4 import BeautifulSoup
from docx import Document
from ebooklib import epub
from odf import text as odf_text
from odf import teletype
from odf.opendocument import load as load_odt
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader
from striprtf.striprtf import rtf_to_text

# Unknown extensions are accepted when they are UTF-8-like text (code, logs, config, etc.).
SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".pptx", ".xls", ".xlsx", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm", ".epub"}


def _rows_from_workbook(workbook) -> str:
    rows: list[str] = []
    for sheet in workbook.worksheets:
        rows.append(f"Sheet: {sheet.title}")
        rows.extend(" | ".join("" if cell is None else str(cell) for cell in row) for row in sheet.iter_rows(values_only=True))
    return "\n".join(rows)


def _convert_legacy_doc(filename: str, content: bytes) -> str:
    """Use a locally installed LibreOffice to convert binary .doc files safely."""
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / filename
        source.write_bytes(content)
        try:
            subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text", "--outdir", temporary, str(source)], check=True, capture_output=True, timeout=60)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise ValueError("Legacy .doc requires LibreOffice. Install it, or save the file as .docx and upload again.") from exc
        converted = source.with_suffix(".txt")
        if not converted.exists():
            raise ValueError("LibreOffice could not convert this .doc file. Save it as .docx and try again.")
        return converted.read_text(encoding="utf-8", errors="replace")


def extract_text(filename: str, content: bytes) -> str:
    """Extract text from office, ebook, structured-data, and generic text files."""
    extension = Path(filename).suffix.lower()
    if extension == ".doc":
        return _convert_legacy_doc(filename, content)
    if extension == ".docx":
        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs)
    if extension == ".odt":
        document = load_odt(io.BytesIO(content))
        return "\n".join(teletype.extractText(node) for node in document.getElementsByType(odf_text.P))
    if extension == ".rtf":
        return rtf_to_text(content.decode("utf-8", errors="replace"))
    if extension == ".pptx":
        presentation = Presentation(io.BytesIO(content))
        return "\n".join(f"Slide {number}: " + " ".join(shape.text for shape in slide.shapes if hasattr(shape, "text")) for number, slide in enumerate(presentation.slides, start=1))
    if extension == ".xlsx":
        return _rows_from_workbook(load_workbook(io.BytesIO(content), read_only=True, data_only=True))
    if extension == ".xls":
        import xlrd
        workbook = xlrd.open_workbook(file_contents=content)
        rows = []
        for sheet in workbook.sheets():
            rows.append(f"Sheet: {sheet.name}")
            rows.extend(" | ".join(str(value) for value in sheet.row_values(row)) for row in range(sheet.nrows))
        return "\n".join(rows)
    if extension in {".csv", ".tsv"}:
        dialect = "excel-tab" if extension == ".tsv" else "excel"
        return "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace")), dialect=dialect))
    if extension == ".json":
        return json.dumps(json.loads(content.decode("utf-8")), ensure_ascii=False, indent=2)
    if extension in {".yaml", ".yml"}:
        return yaml.safe_dump(yaml.safe_load(content.decode("utf-8")), allow_unicode=True, sort_keys=False)
    if extension in {".html", ".htm"}:
        return BeautifulSoup(content, "html.parser").get_text("\n", strip=True)
    if extension == ".xml":
        return "\n".join(piece.strip() for piece in element_tree.fromstring(content).itertext() if piece.strip())
    if extension == ".epub":
        book = epub.read_epub(io.BytesIO(content))
        return "\n".join(BeautifulSoup(item.get_content(), "html.parser").get_text(" ", strip=True) for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    if extension == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    if b"\x00" in content[:4096]:
        raise ValueError(f"'{extension or 'this file'}' is a binary format with no supported text extractor.")
    return content.decode("utf-8-sig", errors="replace")


def extract_documents(filename: str, content: bytes) -> list[dict]:
    """Return page-level PDF records, or one record for every other text-bearing format."""
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return [{"url": f"upload://{filename}", "title": filename, "text": page.extract_text() or "", "page": number} for number, page in enumerate(PdfReader(io.BytesIO(content)).pages, start=1)]
    return [{"url": f"upload://{filename}", "title": filename, "text": extract_text(filename, content)}]
