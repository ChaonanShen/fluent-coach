from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.pdf import MAX_PDF_BYTES, MAX_PDF_TEXT_CHARS, clean_pdf_text, extract_pdf_text


class FakePage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakePdfReader:
    pages = [FakePage("Page one text."), FakePage("Page two text.")]

    def __init__(self, stream) -> None:
        self.stream = stream


def test_upload_known_info_pdf_rejects_non_pdf() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/known-info/pdf",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF files are supported"


def test_upload_known_info_pdf_rejects_large_file() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/known-info/pdf",
        files={"file": ("resume.pdf", b"x" * (MAX_PDF_BYTES + 1), "application/pdf")},
    )

    assert response.status_code == 413
    assert "10MB" in response.json()["detail"]


def test_upload_known_info_pdf_extracts_text(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.services.pdf.PdfReader", FakePdfReader)
    client = TestClient(app)

    response = client.post(
        "/api/known-info/pdf",
        files={"file": ("resume.pdf", b"%PDF fake", "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Page one text.\nPage two text."
    assert body["source"] == {
        "name": "resume.pdf",
        "kind": "pdf",
        "text_preview": "Page one text.\nPage two text.",
        "char_count": len("Page one text.\nPage two text."),
    }


def test_extract_pdf_text_rejects_empty_or_unreadable_pdf(monkeypatch) -> None:
    class EmptyPdfReader:
        pages = [FakePage("  "), FakePage(None)]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setattr("backend.app.services.pdf.PdfReader", EmptyPdfReader)

    try:
        extract_pdf_text(b"%PDF fake")
    except ValueError as exc:
        assert "extractable text" in str(exc)
    else:
        raise AssertionError("Expected empty PDF text to fail")


def test_extract_pdf_text_truncates_to_limit(monkeypatch) -> None:
    class LongPdfReader:
        pages = [FakePage("a" * (MAX_PDF_TEXT_CHARS + 100))]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setattr("backend.app.services.pdf.PdfReader", LongPdfReader)

    text = extract_pdf_text(b"%PDF fake")

    assert len(text) == MAX_PDF_TEXT_CHARS


def test_clean_pdf_text_removes_control_chars_and_collapses_space() -> None:
    text = clean_pdf_text("Hello\x00   world\n\n\nNext\tline")

    assert text == "Hello world\n\nNext line"
