"""Các đường dẫn API mà giao diện (frontend) gọi tới."""
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StrictStr
from nlp.chat import answer_meeting_question
from nlp.errors import SummaryError
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
               "stage": "queued", "timings": {}, "transcript_revision": 0,
               "pipeline_status": "processing",
               "created": datetime.now().isoformat(timespec="seconds"), "sec": 0, "people": 1}
    storage.add_meeting(meeting)
    bg.add_task(process_meeting, mid, src)  # xử lý ở nền, trả lời giao diện ngay
    return meeting

@app.post("/api/meetings/{mid}/retry-summary")
def retry_summary(mid: str, bg: BackgroundTasks):
    """Tóm tắt lại từ transcript đã lưu, không chạy ASR."""
    def begin(m):
        ensure_idle(m)
        if not (m.get("transcript_edited") or m.get("transcript") or "").strip():
            raise HTTPException(409, "Cuộc họp chưa có transcript để tạo biên bản")
        timings = dict(m.get("timings") or {})
        timings.pop("summary_seconds", None)
        return {"summary_status": "processing", "summary_error": None,
                "summary_error_code": None, "stage": "summarizing", "timings": timings}

    m = storage.mutate_meeting(mid, begin)
    if not m:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    bg.add_task(retry_meeting_summary, mid)
    return {"id": mid, "summary_status": "processing"}


def ensure_idle(meeting):
    if (meeting.get("status") == "processing" or meeting.get("summary_status") == "processing"
            or meeting.get("pipeline_status") == "processing"):
        raise HTTPException(409, "Cuộc họp đang được xử lý. Hãy đợi hoàn tất rồi thử lại.")


class TranscriptEdit(BaseModel):
    text: StrictStr = Field(min_length=1, max_length=200000)
    expected_revision: int = Field(ge=0)


@app.patch("/api/meetings/{mid}/transcript")
def edit_transcript(mid: str, body: TranscriptEdit):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Transcript không được để trống")

    def edit(m):
        ensure_idle(m)
        if not (m.get("transcript") or "").strip():
            raise HTTPException(409, "Chưa có transcript gốc để chỉnh sửa")
        revision = m.get("transcript_revision", 0)
        if revision != body.expected_revision:
            raise HTTPException(409, "Transcript đã thay đổi ở cửa sổ khác. Hãy tải lại trước khi lưu.")
        if text == (m.get("transcript_edited") or m["transcript"]):
            return {}
        return {"transcript_edited": text, "transcript_revision": revision + 1,
                "transcript_updated_at": datetime.now().isoformat(timespec="seconds"),
                "summary_outdated": bool(m.get("summary") or m.get("minutes"))}

    meeting = storage.mutate_meeting(mid, edit)
    if meeting is None:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    return meeting
class ChatTurn(BaseModel):
    role: StrictStr
    content: StrictStr


class MeetingChatRequest(BaseModel):
    question: StrictStr = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)


@app.post("/api/meetings/{mid}/chat")
def chat_meeting(mid: str, body: MeetingChatRequest):
    m = storage.get_meeting(mid)
    if not m:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    if not (m.get("transcript_edited") or m.get("transcript") or "").strip():
        raise HTTPException(409, "Cuộc họp chưa có nội dung transcript để hỏi đáp")
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Câu hỏi không được để trống")
    try:
        history = [{"role": t.role, "content": t.content} for t in body.history]
        answer = answer_meeting_question(m, question, history)
        return {"answer": answer}
    except SummaryError as exc:
        raise HTTPException(502, str(exc))
