from __future__ import annotations

# JSON Schema describing the structure of rich blocks used in human notes.
# The schema is intentionally lightweight – it is used for validation and for
# tooling that wants to understand which payload fields are available.

BLOCK_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "HumanNote",
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {"$ref": "#/definitions/block"},
        },
        "meta": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["blocks"],
    "additionalProperties": False,
    "definitions": {
        "richText": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "annotations": {
                    "type": "object",
                    "properties": {
                        "bold": {"type": "boolean"},
                        "italic": {"type": "boolean"},
                        "underline": {"type": "boolean"},
                        "strike": {"type": "boolean"},
                        "code": {"type": "boolean"},
                        "href": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                    "default": {},
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "todoItem": {
            "type": "object",
            "properties": {
                "id": {"type": ["string", "null"]},
                "text": {"type": "string"},
                "done": {"type": "boolean"},
            },
            "required": ["text", "done"],
            "additionalProperties": False,
        },
        "block": {
            "type": "object",
            "properties": {
                "id": {"type": ["string", "null"]},
                "type": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["type", "data"],
            "additionalProperties": False,
            "oneOf": [
                {
                    "properties": {
                        "type": {"const": "heading"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "level": {"type": "integer", "minimum": 1, "maximum": 3},
                                "text": {"type": "string"},
                            },
                            "required": ["level", "text"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "paragraph"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "parts": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/richText"},
                                }
                            },
                            "required": ["parts"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "bulletList"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/richText"},
                                }
                            },
                            "required": ["items"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "numberList"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/richText"},
                                }
                            },
                            "required": ["items"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "quote"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "cite": {"type": ["string", "null"]},
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "image"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "src": {"type": "string"},
                                "full": {"type": ["string", "null"]},
                                "alt": {"type": ["string", "null"]},
                                "w": {"type": ["integer", "null"]},
                                "h": {"type": ["integer", "null"]},
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "audio"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "src": {"type": "string"},
                                "mime": {"type": ["string", "null"]},
                                "duration": {"type": ["number", "null"]},
                                "waveform": {"type": ["string", "null"]},
                                "transcript": {"type": ["string", "null"]},
                                "view": {
                                    "type": "string",
                                    "enum": ["mini", "expanded"],
                                },
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "video"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "src": {"type": "string"},
                                "poster": {"type": ["string", "null"]},
                                "duration": {"type": ["number", "null"]},
                                "w": {"type": ["integer", "null"]},
                                "h": {"type": ["integer", "null"]},
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "doc"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["pdf", "docx", "rtf", "pptx", "txt"],
                                },
                                "src": {"type": "string"},
                                "title": {"type": ["string", "null"]},
                                "preview": {"type": ["string", "null"]},
                                "meta": {
                                    "type": "object",
                                    "properties": {
                                        "pages": {"type": ["integer", "null"]},
                                        "slides": {"type": ["integer", "null"]},
                                        "size": {"type": ["integer", "null"]},
                                        "words": {"type": ["integer", "null"]},
                                    },
                                    "additionalProperties": False,
                                },
                                "view": {
                                    "type": "string",
                                    "enum": ["cover", "inline"],
                                },
                            },
                            "required": ["kind", "src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "slides"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["pptx"]},
                                "src": {"type": "string"},
                                "slides": {"type": ["string", "null"]},  # OVC: pptx - опционально
                                "preview": {"type": ["string", "null"]},
                                "count": {"type": ["integer", "null"], "minimum": 0},
                                "view": {"type": "string", "enum": ["cover", "inline"]},
                            },
                            "required": ["kind", "src"],  # OVC: pptx - slides больше не обязательное
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "sheet"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["xlsx", "csv"]},
                                "src": {"type": "string"},
                                "sheets": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "rows": {"type": ["integer", "null"]},
                            },
                            "required": ["kind", "src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "code"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "language": {"type": ["string", "null"]},
                                "src": {"type": "string"},
                                "lines": {"type": ["integer", "null"]},
                                "sha256": {"type": ["string", "null"]},
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "archive"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "src": {"type": "string"},
                                "tree": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "path": {"type": "string"},
                                            "size": {"type": ["integer", "null"]},
                                        },
                                        "required": ["path"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "link"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "title": {"type": ["string", "null"]},
                                "desc": {"type": ["string", "null"]},
                                "image": {"type": ["string", "null"]},
                            },
                            "required": ["url"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "table"},
                        "data": {
                            "type": "object",
                            "oneOf": [
                                {
                                    "properties": {
                                        "rows": {
                                            "type": "array",
                                            "items": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        }
                                    },
                                    "required": ["rows"],
                                    "additionalProperties": False,
                                },
                                {
                                    "properties": {
                                        "kind": {
                                            "type": "string",
                                            "enum": ["xlsx", "xls", "csv"],
                                        },
                                        "src": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "view": {
                                            "type": "string",
                                            "enum": ["cover", "inline"],
                                        },
                                        "activeSheet": {"type": ["string", "null"]},
                                        "charts": {"type": ["string", "null"]},  # OVC: excel - URL к JSON с метаданными диаграмм
                                    },
                                    "required": ["kind", "src", "summary"],
                                    "additionalProperties": False,
                                },
                            ],
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "source"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "title": {"type": "string"},
                                "domain": {"type": "string"},
                                "published_at": {"type": ["string", "null"]},
                                "summary": {"type": ["string", "null"]},
                            },
                            "required": ["url", "title", "domain"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "summary"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "dateISO": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["dateISO", "text"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "todo"},
                        "data": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/definitions/todoItem"},
                                }
                            },
                            "required": ["items"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "divider"},
                        "data": {
                            "type": "object",
                            "additionalProperties": False,
                        },
                    }
                },
            ],
        },
    },
}
