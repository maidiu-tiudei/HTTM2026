"""Các đường dẫn API mà giao diện (frontend) gọi tới."""
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import storage
from .pipeline import process_meeting, warm_up


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