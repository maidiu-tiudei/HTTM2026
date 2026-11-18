"""Chuẩn hóa audio, phiên âm, tạo biên bản và ghi thời gian từng giai đoạn."""
import json
import subprocess
import threading
import time
from datetime import datetime

import imageio_ffmpeg
import soundfile as sf

import config
from asr.transcriber import _load_pipeline, transcribe_audio, get_asr_runtime
from asr.diarization import identify_turns, speaker_timeline
from nlp.errors import SummaryError, classify_summary_error
from nlp.formatter import format_bien_ban
from nlp.schema import validate_summary
from nlp.summarizer import summarize_transcript
from .storage import OUT, UPLOADS, get_meeting, mutate_meeting, update_meeting

_run_lock = threading.Lock()


def warm_up():
    try:
        with _run_lock:
            _load_pipeline(config.ASR_MODELS.get(config.ASR_MODEL_SIZE, config.ASR_MODELS["small"]))
        print("[ASR] Model ready.")
    except Exception as exc:
        print(f"[ASR] Model load failed: {ascii(str(exc))}")


def to_wav(src, wav):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src), "-ar", "16000", "-ac", "1", str(wav)]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode:
        raise RuntimeError("Không đọc được file audio: " + result.stderr.decode(errors="replace")[-300:])


def record_time(mid, name, started, **fields):
    seconds = round(time.perf_counter() - started, 3)

    def change(meeting):
        timings = dict(meeting.get("timings") or {})
        timings[name] = seconds
        return {"timings": timings, **fields}

    mutate_meeting(mid, change)
    print(f"[{mid}] {name}: {seconds:.3f}s")


def retry_meeting_summary(mid):
    meeting = get_meeting(mid)
    if not meeting:
        return
    transcript = meeting.get("transcript_edited") or meeting.get("transcript") or ""
    started = time.perf_counter()

    def finish(**fields):
        # Trạng thái kết thúc và số đo được lưu cùng lúc để lần poll cuối không thiếu số đo.
        record_time(mid, "summary_seconds", started, **fields)

    update_meeting(mid, stage="summarizing", summary_status="processing",
                   summary_error=None, summary_error_code=None)
    try:
        if not transcript.strip():
            raise SummaryError("invalid_response")
        summary = validate_summary(summarize_transcript(transcript))
        minutes = format_bien_ban(summary)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            (OUT / f"bienban_{ts}.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            (OUT / f"bienban_{ts}.txt").write_text(minutes, encoding="utf-8")
            # Chỉ thay biên bản cũ sau khi kết quả mới hợp lệ và các file đã lưu xong.
            finish(
                status="done", stage="done", summary_status="done",
                summary_error=None, summary_error_code=None, summary=summary, minutes=minutes,
                transcript_clean=summary.get("transcript_chinh_sua"),
                summary_transcript_revision=meeting.get("transcript_revision", 0),
                summary_outdated=False,
                summary_updated_at=datetime.now().isoformat(timespec="seconds"),
            )
        except OSError:
            raise SummaryError("storage_error") from None
    except Exception as exc:
        error = classify_summary_error(exc)
        print(f"[{mid}] Summary failed: {error.code}")
        # Không xóa summary, minutes, transcript_clean của lần thành công trước.
        finish(status="done", stage="summary_error", summary_status="error",
               summary_error=str(error), summary_error_code=error.code)


def save_speaker_timeline(mid, wav, segments=None):
    """Xử lý riêng lỗi phân vai để giữ transcript và biên bản hiện có."""
    started = time.perf_counter()
    try:
        if segments is None:
            with _run_lock:
                _, segments = transcribe_audio(str(wav), include_segments=True)
        if not segments:
            raise RuntimeError("Bộ phiên âm chưa trả mốc thời gian cho file này.")
        timeline = speaker_timeline(segments, identify_turns(wav))
        count = len({row["speaker_id"] for row in timeline if row["speaker_id"]})
        record_time(mid, "speaker_seconds", started, speaker_status="done", speaker_error=None,
                    speaker_segments=timeline, speaker_count=count, people=count or None, speaker_names={},
                    speaker_version=datetime.now().isoformat(timespec="microseconds"))
    except Exception as exc:
        print(f"[{mid}] Speaker analysis failed: {ascii(str(exc))}")
        message = str(exc) if str(exc).startswith(("Chưa có model", "Chưa cài sherpa", "Bộ phiên âm")) else "Không tách được người nói từ audio này. Bạn có thể thử lại."
        record_time(mid, "speaker_seconds", started, speaker_status="error", speaker_error=message)


def process_meeting(mid, src):
    pipeline_started = time.perf_counter()
    stage = "converting"
    try:
        wav = UPLOADS / f"{mid}.wav"
        update_meeting(mid, stage=stage, pipeline_status="processing")
        started = time.perf_counter()
        try:
            to_wav(src, wav)
            update_meeting(mid, sec=round(sf.info(str(wav)).duration))
        finally:
            record_time(mid, "conversion_seconds", started)

        stage = "waiting_asr"
        update_meeting(mid, stage=stage)
        started = time.perf_counter()
        with _run_lock:
            record_time(mid, "queue_seconds", started)
            stage = "transcribing"
            update_meeting(mid, stage=stage)
            started = time.perf_counter()
            try:
                transcript, segments = transcribe_audio(str(wav), include_segments=True)
                update_meeting(mid, asr_runtime=get_asr_runtime())
            finally:
                record_time(mid, "asr_seconds", started)
        if not transcript or not transcript.strip():
            raise RuntimeError("Không nhận diện được lời nói trong file âm thanh")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        (OUT / f"transcript_{ts}.txt").write_text(transcript, encoding="utf-8")
        update_meeting(mid, transcript=transcript, transcript_revision=0,
                       status="done", stage="diarizing", speaker_status="processing")
        save_speaker_timeline(mid, wav, segments)
        retry_meeting_summary(mid)
    except Exception as exc:
        update_meeting(mid, status="error", stage="error", failed_stage=stage,
                       error=str(exc)[:300], summary_status="error")
    finally:
        # Đây là thời gian lượt xử lý audio ban đầu, không cộng lẫn các lần tạo lại.
        record_time(mid, "initial_pipeline_seconds", pipeline_started, pipeline_status="done")
