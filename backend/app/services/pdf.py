from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader


MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 6000


class PdfExtractionError(ValueError):
    pass


def extract_pdf_text(file_bytes: bytes, *, max_chars: int = MAX_PDF_TEXT_CHARS) -> str:
    if not file_bytes:
        raise PdfExtractionError("PDF file is empty")
    try:
        reader = PdfReader(BytesIO(file_bytes))
    except Exception as exc:
        raise PdfExtractionError("Could not read PDF text") from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(text)
    cleaned = clean_pdf_text("\n".join(parts))
    if not cleaned:
        raise PdfExtractionError("PDF does not contain extractable text")
    return cleaned[:max_chars]


def clean_pdf_text(text: str) -> str:
    without_control_chars = "".join(char for char in text if char == "\n" or char == "\t" or ord(char) >= 32)
    collapsed = re.sub(r"[ \t\r\f\v]+", " ", without_control_chars)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()
