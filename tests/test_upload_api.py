from __future__ import annotations

import sys
import unittest
from pathlib import Path
import base64

import base64
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


PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFUlEQVR4nGP8z/D/PwMDAwMjI"
    "gYABq0DC+4SS64AAAAASUVORK5CYII="
)


def make_png() -> bytes:
    return base64.b64decode(PNG_BASE64)


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
        self.assertIn("blocks", data)
        self.assertTrue(data["blocks"])
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
        block = response.json()["blocks"][0]
        self.assertEqual(block["type"], "doc")
        self.assertEqual(block["data"]["kind"], "pdf")
        self.assertTrue(block["data"]["src"].endswith("/original"))


if __name__ == "__main__":
    unittest.main()
