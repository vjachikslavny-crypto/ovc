from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simple_app"))

from app.agent.block_models import parse_blocks  # noqa: E402
from app.api.note_models import NoteCreateRequest  # noqa: E402


class BlockModelParsingTests(unittest.TestCase):
    def test_parse_media_blocks(self):
        blocks = [
            {
                "type": "image",
                "data": {"src": "/files/1/preview.webp", "w": 800, "h": 600},
            },
            {
                "type": "doc",
                "data": {"kind": "pdf", "src": "/files/2/original"},
            },
            {
                "type": "sheet",
                "data": {"kind": "csv", "src": "/files/3/original", "rows": 10},
            },
        ]

        parsed = parse_blocks(blocks)

        self.assertEqual(parsed[0].type, "image")
        self.assertEqual(parsed[1].data.kind, "pdf")
        self.assertEqual(parsed[2].data.kind, "csv")

    def test_parse_audio_block(self):
        blocks = [
            {
                "type": "audio",
                "data": {
                    "src": "/files/a1/stream",
                    "mime": "audio/webm",
                    "duration": 12.5,
                    "waveform": "/files/a1/waveform",
                    "view": "expanded",
                },
            }
        ]

        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].data.view, "expanded")

    def test_parse_slides_block(self):
        blocks = [
            {
                "type": "slides",
                "data": {
                    "kind": "pptx",
                    "src": "/files/s1/original",
                    "slides": "/files/s1/slides.json",
                    "preview": "/files/s1/slide/1",
                    "count": 5,
                    "view": "inline",
                },
            }
        ]

        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].data.count, 5)

    def test_parse_doc_block_with_view(self):
        blocks = [
            {
                "type": "doc",
                "data": {
                    "kind": "docx",
                    "src": "/files/4/original",
                    "view": "inline",
                },
            }
        ]

        parsed = parse_blocks(blocks)

        self.assertEqual(parsed[0].data.kind, "docx")
        self.assertEqual(parsed[0].data.view, "inline")

    def test_parse_video_block(self):
        blocks = [
            {
                "type": "video",
                "data": {
                    "src": "/files/v1/video/source",
                    "poster": "/files/v1/video/poster.webp",
                    "durationSec": 12,
                    "width": 1280,
                    "height": 720,
                    "mime": "video/mp4",
                    "view": "inline",
                },
            }
        ]
        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].type, "video")
        self.assertEqual(parsed[0].data.duration_sec, 12)

    def test_parse_youtube_block(self):
        blocks = [
            {
                "type": "youtube",
                "data": {
                    "videoId": "abcdefghijk",
                    "startSec": 47,
                    "view": "cover",
                },
            }
        ]
        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].type, "youtube")
        self.assertEqual(parsed[0].data.video_id, "abcdefghijk")
        self.assertEqual(parsed[0].data.view, "cover")

    def test_parse_table_block_with_summary(self):
        blocks = [
            {
                "type": "table",
                "data": {
                    "kind": "xlsx",
                    "src": "/files/t1/original",
                    "summary": "/files/t1/excel/summary.json",
                    "view": "cover",
                    "activeSheet": "Sheet1",
                },
            }
        ]

        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].type, "table")
        self.assertEqual(parsed[0].data.summary, "/files/t1/excel/summary.json")

    def test_parse_code_block(self):
        blocks = [
            {
                "type": "code",
                "data": {
                    "src": "/files/c1/code/raw",
                    "previewUrl": "/files/c1/code/preview?maxLines=300",
                    "filename": "demo.py",
                    "language": "python",
                    "sizeBytes": 120,
                    "lineCount": 10,
                    "view": "inline",
                },
            }
        ]

        parsed = parse_blocks(blocks)
        self.assertEqual(parsed[0].type, "code")
        self.assertEqual(parsed[0].data.language, "python")

    def test_table_block_requires_summary(self):
        with self.assertRaises(ValidationError):
            parse_blocks(
                [
                    {
                        "type": "table",
                        "data": {
                            "kind": "csv",
                            "src": "/files/t2/original",
                        },
                    }
                ]
            )

    def test_parse_invalid_block_type(self):
        blocks = [{"type": "unknown", "data": {}}]
        with self.assertRaises(ValidationError):
            parse_blocks(blocks)


class NoteRequestValidationTests(unittest.TestCase):
    def test_create_request_validates_blocks(self):
        payload = NoteCreateRequest(
            title="Test",
            styleTheme="clean",
            blocks=[
                {
                    "type": "heading",
                    "data": {"level": 1, "text": "Intro"},
                },
                {
                    "type": "code",
                    "data": {
                        "src": "/files/code/raw",
                        "previewUrl": "/files/code/preview?maxLines=300",
                        "filename": "demo.py",
                        "language": "python",
                    },
                },
            ],
        )

        self.assertEqual(len(payload.blocks), 2)
        self.assertEqual(payload.blocks[0].type, "heading")
        self.assertEqual(payload.blocks[1].data.language, "python")

    def test_create_request_rejects_bad_block(self):
        with self.assertRaises(ValidationError):
            NoteCreateRequest(
                title="Broken",
                styleTheme="clean",
                blocks=[{"type": "heading", "data": {"level": 5, "text": "oops"}}],
            )


if __name__ == "__main__":
    unittest.main()
