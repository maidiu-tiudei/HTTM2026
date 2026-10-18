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


def process_meeting(mid, src):
    try:
        wav = UPLOADS / f"{mid}.wav"
        to_wav(src, wav)
        update_meeting(mid, sec=round(sf.info(str(wav)).duration))

        with _run_lock:
            transcript = transcribe_audio(str(wav))

        # Gemini lỗi thì vẫn giữ transcript, chỉ thiếu biên bản
        summary, minutes = None, "Chưa có biên bản (thiếu GEMINI_API_KEY)."
        try:
            summary = summarize_transcript(transcript)  # None nếu thiếu API key
            if summary:
                minutes = format_bien_ban(summary)
        except Exception as e:
            minutes = f"Chưa có biên bản vì lỗi khi tóm tắt: {str(e)[:300]}"

        # Lưu file giống main.py để cả nhóm xem lại được
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (OUT / f"transcript_{ts}.txt").write_text(transcript, encoding="utf-8")
        if summary:
            (OUT / f"bienban_{ts}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / f"bienban_{ts}.txt").write_text(minutes, encoding="utf-8")

        update_meeting(mid, status="done", transcript=transcript, minutes=minutes)
    except Exception as e:
        update_meeting(mid, status="error", error=str(e)[:500])