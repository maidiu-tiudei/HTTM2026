"""Lưu và đọc danh sách cuộc họp trong meeting_outputs/meetings.json."""
import json
import threading
import os
import tempfile
from copy import deepcopy
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
    # Chỉ thay DB sau khi ghi xong file tạm; tránh làm rỗng dữ liệu cũ nếu ghi lỗi.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=DB.parent,
                                         prefix=DB.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(items, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, DB)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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


def mutate_meeting(mid, change):
    """Kiểm tra và cập nhật trong cùng khóa, tránh yêu cầu đồng thời đè nhau."""
    with _lock:
        items = _read()
        meeting = next((item for item in items if item["id"] == mid), None)
        if meeting is None:
            return None
        meeting.update(change(deepcopy(meeting)))
        _write(items)
        return deepcopy(meeting)
