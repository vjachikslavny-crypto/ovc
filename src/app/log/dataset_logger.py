from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_PATH = Path(os.getenv("SIMPLE_DATASET_LOG", str(BASE_DIR / "dataset.log")))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def append(record: Dict[str, Any]) -> None:
    payload = {
        **record,
        "ts": record.get("ts") or datetime.utcnow().isoformat()
    }
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def export(from_ts: Optional[str] = None, to_ts: Optional[str] = None) -> str:
    if not LOG_PATH.exists():
        return ""
    lines: list[str] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = data.get("ts")
        if from_ts and ts and ts < from_ts:
            continue
        if to_ts and ts and ts > to_ts:
            continue
        lines.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(lines)
