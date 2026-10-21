"""Xử lý một cuộc họp: đổi sang wav → chuyển thành chữ → tóm tắt → lưu kết quả."""
import json
import subprocess
import threading
from datetime import datetime

import imageio_ffmpeg
import soundfile as sf

import config
from asr.transcriber import _load_pipeline, transcribe_audio
from nlp.formatter import format_bien_ban
from nlp.summarizer import summarize_transcript
from .storage import OUT, UPLOADS, update_meeting

_run_lock = threading.Lock()  # PhoWhisper chỉ chạy 1 việc một lúc


def warm_up():
    """Nạp model ngay khi bật server để cuộc họp đầu tiên không phải chờ."""
    try:
        with _run_lock:
            _load_pipeline(config.ASR_MODELS.get(config.ASR_MODEL_SIZE, config.ASR_MODELS["small"]))
        print("✅ Model đã sẵn sàng.")
    except Exception as e:
        print(f"⚠️ Chưa nạp được model: {e}")


def to_wav(src, wav):
    """Đổi mọi định dạng (mp4, webm, mp3...) sang wav 16kHz mono."""
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode:
        raise RuntimeError("Không đọc được file audio: " + r.stderr.decode(errors="replace")[-300:])


def retry_meeting_summary(mid):
    """Tạo biên bản từ transcript đã lưu, không xử lý âm thanh lần nữa."""
    from .storage import get_meeting
    meeting = get_meeting(mid)
    if not meeting or not (meeting.get("transcript") or "").strip():
        update_meeting(mid, summary_status="error", summary_error="Không có transcript để tóm tắt")
        return
    transcript = meeting["transcript"]
    try:
        summary = summarize_transcript(transcript)
        if not isinstance(summary, dict) or not summary:
            raise RuntimeError("Gemini không trả về biên bản hợp lệ. Kiểm tra GEMINI_API_KEY.")
        minutes = format_bien_ban(summary)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (OUT / f"bienban_{ts}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / f"bienban_{ts}.txt").write_text(minutes, encoding="utf-8")
        update_meeting(mid, status="done", summary_status="done", summary_error=None,
                       summary=summary, minutes=minutes,
                       transcript_clean=summary.get("transcript_chinh_sua"))
    except Exception as exc:
        print(f"[Gemini] Không tạo được biên bản cho {mid}: {exc}")
        update_meeting(mid, status="done", summary_status="error",
                       summary_error="Dịch vụ tóm tắt tạm thời không khả dụng. Hãy thử lại sau.",
                       summary=None, minutes=None, transcript_clean=None)


def process_meeting(mid, src):
    try:
        wav = UPLOADS / f"{mid}.wav"
        to_wav(src, wav)
        update_meeting(mid, sec=round(sf.info(str(wav)).duration))
        with _run_lock:
            transcript = transcribe_audio(str(wav))
        if not transcript or not transcript.strip():
            raise RuntimeError("Không nhận diện được lời nói trong file âm thanh")
        # Hiện transcript ngay khi ASR xong; không phụ thuộc tốc độ Gemini.
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (OUT / f"transcript_{ts}.txt").write_text(transcript, encoding="utf-8")
        update_meeting(mid, transcript=transcript, status="done", summary_status="processing")
        retry_meeting_summary(mid)
    except Exception as exc:
        update_meeting(mid, status="error", error=str(exc)[:300], summary_status="error")
