"""Các đường dẫn API mà giao diện (frontend) gọi tới."""
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import storage
from .pipeline import process_meeting, warm_up, retry_meeting_summary


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=warm_up, daemon=True).start()  # nạp model ở nền
    yield


app = FastAPI(title="TinaMeetNote API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/meetings")
def list_meetings():
    return storage.all_meetings()


@app.get("/api/meetings/{mid}")
def get_meeting(mid: str):
    m = storage.get_meeting(mid)
    if not m:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    return m


@app.post("/api/meetings")
async def create_meeting(bg: BackgroundTasks, title: str = Form(...), description: str = Form(""),
                         file: UploadFile = File(...)):
    mid = uuid.uuid4().hex[:8]
    src = storage.UPLOADS / f"{mid}{Path(file.filename or '').suffix or '.bin'}"
    src.write_bytes(await file.read())
    meeting = {"id": mid, "title": title, "description": description, "status": "processing",
               "created": datetime.now().isoformat(timespec="seconds"), "sec": 0, "people": 1}
    storage.add_meeting(meeting)
    bg.add_task(process_meeting, mid, src)  # xử lý ở nền, trả lời giao diện ngay
    return meeting

@app.post("/api/meetings/{mid}/retry-summary")
def retry_summary(mid: str, bg: BackgroundTasks):
    """Tóm tắt lại từ transcript đã lưu, không chạy ASR."""
    m = storage.get_meeting(mid)
    if not m:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    if not (m.get("transcript") or "").strip():
        raise HTTPException(409, "Cuộc họp chưa có transcript để tạo biên bản")
    if m.get("summary_status") == "processing" or m.get("status") == "processing":
        raise HTTPException(409, "Cuộc họp đang được xử lý")
    storage.update_meeting(mid, summary_status="processing", summary_error=None)
    bg.add_task(retry_meeting_summary, mid)
    return {"id": mid, "summary_status": "processing"}
