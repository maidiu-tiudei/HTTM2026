"""Speech-to-Text bằng PhoWhisper (Người A)."""
import time
from functools import lru_cache

import numpy as np

import config

_runtime_info = {}


def get_asr_runtime():
    return dict(_runtime_info)


@lru_cache(maxsize=1)
def _load_pipeline(model_name):
    """Chỉ tải model 1 lần cho mỗi tiến trình (quan trọng khi chạy backend: không tải lại mỗi request)."""
    if config.ASR_BACKEND == "faster-whisper":
        from asr.fast_runtime import load_faster_model
        model, info = load_faster_model(model_name)
        _runtime_info.clear()
        _runtime_info.update(info)
        return model
    if config.ASR_BACKEND != "transformers":
        raise ValueError("ASR_BACKEND chỉ nhận transformers hoặc faster-whisper")
    from transformers import pipeline
    print(f"[ASR] Loading transformers model: {model_name}")
    model = pipeline("automatic-speech-recognition", model=model_name)
    _runtime_info.clear()
    _runtime_info.update(backend="transformers", model=model_name, device=str(model.device),
                         compute_type=str(model.model.dtype))
    return model


def _prepare_audio(audio_path):
    """Đọc, về mono 16kHz, cắt khoảng lặng. Trả (data, sr, bounds)."""
    import soundfile as sf
    import librosa

    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)

    # Resample về 16kHz bằng librosa (không phụ thuộc torchaudio)
    if sr != config.SAMPLE_RATE:
        data = librosa.resample(data, orig_sr=sr, target_sr=config.SAMPLE_RATE)
        sr = config.SAMPLE_RATE

    # Cắt khoảng lặng đầu/cuối: nguyên nhân phổ biến gây lặp từ (hallucination)
    data, bounds = librosa.effects.trim(data, top_db=30)
    if not data.size or not np.any(data):
        raise ValueError("Audio trống hoặc không có tín hiệu âm thanh")
    return data, sr, bounds


def _normalize(data):
    """Chuẩn hóa âm lượng để model nghe rõ hơn khi ghi âm nhỏ."""
    peak = float(np.max(np.abs(data)))
    return data / peak * 0.9 if peak > 0 else data


def _clean(text):
    return text.replace("\ufffd", "").strip()


def transcribe_audio(audio_path, model_size=None, *, include_segments=False):
    """Chuyển file audio (wav/mp3...) thành văn bản (hoặc tuple (transcript, rows) nếu include_segments=True)."""
    model_size = model_size or config.ASR_MODEL_SIZE
    model_name = config.ASR_MODELS.get(model_size, config.ASR_MODELS["small"])
    asr = _load_pipeline(model_name)

    data, sr, bounds = _prepare_audio(audio_path)
    duration = len(data) / sr

    print("[ASR] Transcribing audio...")
    start = time.time()
    if config.ASR_BACKEND == "faster-whisper":
        from asr.fast_runtime import transcribe_faster
        result = transcribe_faster(asr, data, include_segments=include_segments)
        print(f"[ASR] Transcript complete ({time.time() - start:.1f}s).")
        if not include_segments:
            return _clean(result)
        transcript, rows = result
        transcript = _clean(transcript)
    else:
        options = {"return_timestamps": True} if duration > 30 or include_segments else {}
        result = asr(
            {"array": _normalize(data), "sampling_rate": sr},
            generate_kwargs={"language": "vi", "task": "transcribe", "num_beams": 1,
                             "no_repeat_ngram_size": 3, "repetition_penalty": 1.3},
            **options,
        )
        print(f"[ASR] Transcript complete ({time.time() - start:.1f}s).")
        transcript = _clean(result["text"])
        if not include_segments:
            return transcript
        rows = [{"start": chunk_start, "end": duration if chunk_end is None else chunk_end,
                 "text": _clean(chunk["text"])}
                for chunk in result.get("chunks", [])
                for chunk_start, chunk_end in [chunk["timestamp"]]
                if chunk_start is not None and _clean(chunk["text"])]
        if not rows and transcript:
            rows = [{"start": 0.0, "end": duration, "text": transcript}]

    # Mốc được tính trên đoạn đã cắt im lặng. Đổi về trục thời gian của file phát.
    offset = bounds[0] / sr
    for row in rows:
        row["text"] = _clean(row["text"])
        for unit in [row, *row.get("words", [])]:
            unit["start"] = round(offset + max(0.0, min(duration, float(unit["start"]))), 3)
            unit["end"] = round(offset + max(0.0, min(duration, float(unit["end"]))), 3)
    return transcript, rows


def transcribe_segments(audio_path, model_size=None):
    """Tương thích hàm cũ: trả [{'start','end','text'}] với mốc thời gian khớp file wav gốc."""
    _, rows = transcribe_audio(audio_path, model_size=model_size, include_segments=True)
    return [{"start": r["start"], "end": r["end"], "text": r["text"]} for r in rows]