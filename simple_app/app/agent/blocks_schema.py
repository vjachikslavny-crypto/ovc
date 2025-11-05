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
                                "alt": {"type": ["string", "null"]},
                                "caption": {"type": ["string", "null"]},
                            },
                            "required": ["src"],
                            "additionalProperties": False,
                        },
                    }
                },
                {
                    "properties": {
                        "type": {"const": "table"},
                        "data": {
                            "type": "object",
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

