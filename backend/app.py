"""Các đường dẫn API mà giao diện (frontend) gọi tới."""
import threading
import uuid
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictStr

from . import storage
from .pipeline import process_meeting, warm_up, retry_meeting_summary, save_speaker_timeline
from nlp.errors import classify_summary_error
from nlp.meeting_chat import answer_meeting


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
    return {**m, "audio_available": meeting_wav(mid) is not None}


def meeting_wav(mid):
    if not re.fullmatch(r"[a-f0-9]{8}", mid):
        return None
    path = storage.UPLOADS / f"{mid}.wav"
    return path if path.is_file() else None


@app.get("/api/meetings/{mid}/audio")
def get_meeting_audio(mid: str):
    meeting = storage.get_meeting(mid)
    wav = meeting_wav(mid) if meeting and meeting.get("transcript") else None
    if not wav:
        raise HTTPException(404, "Không tìm thấy bản audio của cuộc họp.")
    return FileResponse(wav, media_type="audio/wav")


@app.post("/api/meetings/{mid}/speakers", status_code=202)
def analyze_speakers(mid: str, bg: BackgroundTasks):
    wav = meeting_wav(mid)

    def begin(m):
        ensure_idle(m)
        if not wav or not m.get("transcript"):
            raise HTTPException(409, "Cần bản audio đã phiên âm để tách người nói.")
        return {"speaker_status": "processing", "speaker_error": None}

    if storage.mutate_meeting(mid, begin) is None:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    bg.add_task(save_speaker_timeline, mid, wav)
    return {"speaker_status": "processing"}


class SpeakerNameEdit(BaseModel):
    name: StrictStr = Field(max_length=80)
    expected_speaker_version: StrictStr | None = None


@app.patch("/api/meetings/{mid}/speakers/{speaker_id}")
def edit_speaker_name(mid: str, speaker_id: str, body: SpeakerNameEdit):
    name = " ".join(body.name.split())

    def edit(m):
        ensure_idle(m)
        if m.get("speaker_version") != body.expected_speaker_version:
            raise HTTPException(409, "Danh sách người nói đã thay đổi. Hãy tải lại cuộc họp rồi thử lại.")
        if not any(row.get("speaker_id") == speaker_id for row in (m.get("speaker_segments") or [])):
            raise HTTPException(404, "Không tìm thấy người nói trong cuộc họp")
        names = dict(m.get("speaker_names") or {})
        if name:
            names[speaker_id] = name
        else:
            names.pop(speaker_id, None)
        return {"speaker_names": names}

    meeting = storage.mutate_meeting(mid, edit)
    if meeting is None:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    return {"speaker_names": meeting["speaker_names"]}


class ChatTurn(BaseModel):
    question: StrictStr = Field(min_length=1, max_length=1200)
    answer: StrictStr = Field(min_length=1, max_length=6000)


class ChatQuestion(BaseModel):
    question: StrictStr = Field(min_length=1, max_length=1200)
    history: list[ChatTurn] = Field(default_factory=list, max_length=4)


@app.post("/api/meetings/{mid}/chat")
def chat_meeting(mid: str, body: ChatQuestion):
    m = storage.get_meeting(mid)
    if not m:
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    if not (m.get("transcript_edited") or m.get("transcript") or "").strip():
        raise HTTPException(409, "Cần transcript trước khi hỏi về cuộc họp.")
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Hãy nhập câu hỏi.")
    try:
        return answer_meeting(m, question, [turn.model_dump() for turn in body.history])
    except Exception as exc:
        error = classify_summary_error(exc)
        status = 429 if error.code == "rate_limit" else 504 if error.code == "timeout" else 502
        if error.code == "missing_key":
            status = 503
        detail = "Chưa hỏi đáp được. Hãy thử lại." if error.code in ("unknown", "invalid_response") else str(error)
        raise HTTPException(status, detail) from None


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
            or meeting.get("pipeline_status") == "processing" or meeting.get("speaker_status") == "processing"):
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
