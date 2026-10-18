"""Lưu và đọc danh sách cuộc họp trong meeting_outputs/meetings.json."""
import json
import threading
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / config.OUTPUT_DIR
UPLOADS = OUT / "uploads"
DB = OUT / "meetings.json"
UPLOADS.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()


def _read():
    return json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else []


def _write(items):
    DB.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def all_meetings():
    with _lock:
        return _read()


def get_meeting(mid):
    return next((m for m in all_meetings() if m["id"] == mid), None)


def add_meeting(meeting):
    with _lock:
        items = _read()
        items.append(meeting)
        _write(items)


def update_meeting(mid, **fields):
    with _lock:
        items = _read()
        for m in items:
            if m["id"] == mid:
                m.update(fields)
        _write(items)