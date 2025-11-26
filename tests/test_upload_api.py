from __future__ import annotations

import base64
import io
import math
import struct
import sys
import unittest
import wave
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simple_app"))

try:
    from app.main import app  # noqa: E402
    from app.db import migrate as db_migrate  # noqa: E402

    _APP_IMPORT_ERROR = None
    db_migrate.upgrade()
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


def make_csv() -> bytes:
    return b"col1,col2\n1,alpha\n2,beta\n3,gamma\n"


def make_wav(duration: float = 0.4) -> bytes:
    buffer = io.BytesIO()
    sample_rate = 16000
    amplitude = 0.3
    frequency = 440
    total_frames = int(sample_rate * duration)
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_frames):
            sample = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * (i / sample_rate)))
            frames.extend(struct.pack('<h', sample))
        wav_file.writeframes(bytes(frames))
    return buffer.getvalue()


def make_fake_mp4() -> bytes:
    # Минимальный контейнер MP4 с заголовком ftyp и пустым mdat
    header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    mdat = b"\x00\x00\x00\x08mdat\x00\x00\x00\x00"
    return header + mdat


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

    def test_upload_audio_creates_block(self):
        wav_bytes = make_wav()
        response = client.post(
            "/api/upload",
            files={"files": ("tone.wav", wav_bytes, "audio/wav")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "audio")
        self.assertIn("src", block["data"])
        file_id = payload["files"][0]["id"]
        waveform = client.get(f"/files/{file_id}/waveform")
        self.assertEqual(waveform.status_code, 200)

    def test_upload_video_creates_block(self):
        video_bytes = make_fake_mp4()
        response = client.post(
            "/api/upload",
            files={"files": ("clip.mp4", video_bytes, "video/mp4")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "video")
        self.assertTrue(block["data"]["src"].endswith("/video/source"))
        poster_url = block["data"].get("poster")
        self.assertTrue(poster_url is None or poster_url.endswith(".webp"))

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

    def test_upload_csv_provides_table_summary_and_window(self):
        csv_bytes = make_csv()
        response = client.post(
            "/api/upload",
            files={"files": ("data.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        block = payload["blocks"][0]
        self.assertEqual(block["type"], "table")
        self.assertEqual(block["data"]["kind"], "csv")
        summary_url = block["data"]["summary"]
        self.assertTrue(summary_url.startswith("/files/"))
        file_id = payload["files"][0]["id"]

        summary_response = client.get(summary_url)
        self.assertEqual(summary_response.status_code, 200)
        summary = summary_response.json()
        self.assertIn("sheets", summary)
        self.assertGreaterEqual(len(summary["sheets"]), 1)
        sheet_name = summary["sheets"][0]["name"]

        window = client.get(f"/files/{file_id}/excel/sheet/{sheet_name}.json?offset=0&limit=2")
        self.assertEqual(window.status_code, 200)
        window_json = window.json()
        self.assertEqual(window_json["offset"], 0)
        self.assertEqual(window_json["limit"], 2)
        self.assertEqual(window_json["columns"], ["col1", "col2"])
        self.assertEqual(len(window_json["rows"]), 2)
        self.assertEqual(window_json["rows"][0], ["1", "alpha"])

        download = client.get(f"/files/{file_id}/excel/sheet/{sheet_name}.csv")
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.headers["content-type"].startswith("text/csv"))


if __name__ == "__main__":
    unittest.main()
