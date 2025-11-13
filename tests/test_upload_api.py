from __future__ import annotations

import base64
import io
import sys
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simple_app"))

try:
    from app.main import app  # noqa: E402

    _APP_IMPORT_ERROR = None
    client = TestClient(app)
except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing on CI
    _APP_IMPORT_ERROR = exc
    app = None
    client = None

try:  # pragma: no cover
    import mammoth  # noqa: F401
    MAMMOTH_AVAILABLE = True
except Exception:  # pragma: no cover
    MAMMOTH_AVAILABLE = False

try:  # pragma: no cover
    from striprtf.striprtf import rtf_to_text as _rtf_check  # noqa: F401
    STRIPRTF_AVAILABLE = True
except Exception:  # pragma: no cover
    STRIPRTF_AVAILABLE = False


PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFUlEQVR4nGP8z/D/PwMDAwMjIgYABq0DC+4SS64AAAAASUVORK5CYII="
)


def make_png() -> bytes:
    return base64.b64decode(PNG_BASE64)


def make_simple_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                <Default Extension="xml" ContentType="application/xml"/>
                <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            </Types>""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                <Relationship Id="R1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
            </Relationships>""",
        )
        docx.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body>
                    <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
                </w:body>
            </w:document>""",
        )
        docx.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>""",
        )
    return buffer.getvalue()


def make_simple_rtf() -> bytes:
    return b"{\\rtf1\\ansi Hello RTF!}"


@unittest.skipIf(client is None, f"FastAPI app unavailable: {_APP_IMPORT_ERROR}")
class UploadApiTests(unittest.TestCase):
    def test_upload_image_returns_block(self):
        payload = make_png()
        response = client.post(
            "/api/upload",
            files={"files": ("tiny.png", payload, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["blocks"])
        self.assertTrue(data["files"])
        block = data["blocks"][0]
        self.assertEqual(block["type"], "image")
        self.assertIn("src", block["data"])
        self.assertTrue(block["data"]["src"].startswith("/files/"))

    def test_upload_rejects_large_image(self):
        payload = b"\xff" * (16 * 1024 * 1024)
        response = client.post(
            "/api/upload",
            files={"files": ("huge.png", payload, "image/png")},
        )
        self.assertEqual(response.status_code, 413)

    def test_upload_rejects_plain_text(self):
        response = client.post(
            "/api/upload",
            files={"files": ("note.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)

    def test_upload_pdf_creates_doc_block(self):
        pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
        response = client.post(
            "/api/upload",
            files={"files": ("demo.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "doc")
        self.assertEqual(block["data"]["kind"], "pdf")
        self.assertTrue(block["data"]["src"].endswith("/original"))

    @unittest.skipUnless(MAMMOTH_AVAILABLE, "mammoth dependency is missing")
    def test_upload_docx_exposes_inline_preview(self):
        docx_bytes = make_simple_docx()
        response = client.post(
            "/api/upload",
            files={"files": ("demo.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "doc")
        self.assertEqual(block["data"]["kind"], "docx")
        file_id = payload["files"][0]["id"]
        html_response = client.get(f"/files/{file_id}/doc.html")
        self.assertEqual(html_response.status_code, 200)
        self.assertIn("Hello DOCX", html_response.text)

    @unittest.skipUnless(STRIPRTF_AVAILABLE, "striprtf dependency is missing")
    def test_upload_rtf_exposes_inline_preview(self):
        rtf_bytes = make_simple_rtf()
        response = client.post(
            "/api/upload",
            files={"files": ("demo.rtf", rtf_bytes, "application/rtf")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "doc")
        self.assertEqual(block["data"]["kind"], "rtf")
        file_id = payload["files"][0]["id"]
        html_response = client.get(f"/files/{file_id}/doc.html")
        self.assertEqual(html_response.status_code, 200)
        self.assertIn("Hello RTF", html_response.text)


if __name__ == "__main__":
    unittest.main()
