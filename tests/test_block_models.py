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
                    "data": {"language": "python", "src": "/files/code.py"},
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
