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
    """Đọc, về mono 16kHz, cắt khoảng lặng. Trả (data, sr, trim_offset_giây)."""
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
    data, idx = librosa.effects.trim(data, top_db=30)
    if not data.size or not np.any(data):
        raise ValueError("Audio trống hoặc không có tín hiệu âm thanh")
    return data, sr, idx[0] / sr


def _normalize(data):
    """Chuẩn hóa âm lượng để model nghe rõ hơn khi ghi âm nhỏ."""
    peak = float(np.max(np.abs(data)))
    return data / peak * 0.9 if peak > 0 else data


def _clean(text):
    return text.replace("\ufffd", "").strip()


def _run_transformers(asr, data, sr):
    """Chạy pipeline transformers với tham số hợp với tiếng Việt, có timestamps."""
    return asr(
        {"array": data, "sampling_rate": sr},
        return_timestamps=True, chunk_length_s=30,
        generate_kwargs={"language": "vi", "task": "transcribe", "num_beams": 1},
    )


def transcribe_audio(audio_path, model_size=None):
    """Chuyển file audio (wav/mp3...) thành văn bản."""
    model_size = model_size or config.ASR_MODEL_SIZE
    model_name = config.ASR_MODELS.get(model_size, config.ASR_MODELS["small"])
    asr = _load_pipeline(model_name)

    data, sr, _ = _prepare_audio(audio_path)

    print("[ASR] Transcribing audio...")
    start = time.time()
    if config.ASR_BACKEND == "faster-whisper":
        from asr.fast_runtime import transcribe_faster
        text = transcribe_faster(asr, data)
        print(f"[ASR] Transcript complete ({time.time() - start:.1f}s).")
        return text

    result = _run_transformers(asr, _normalize(data), sr)
    print(f"[ASR] Transcript complete ({time.time() - start:.1f}s).")
    return _clean(result["text"])


def transcribe_segments_hf(audio_path, model_size=None):
    """Bản dùng transformers (máy không có CTranslate2): trả [{'start','end','text'}]."""
    model_size = model_size or config.ASR_MODEL_SIZE
    model_name = config.ASR_MODELS.get(model_size, config.ASR_MODELS["small"])
    asr = _load_pipeline(model_name)
    data, sr, offset = _prepare_audio(audio_path)
    data = _normalize(data)
    print("[ASR] Transcribing audio (segments, transformers)...")
    start_time = time.time()
    result = _run_transformers(asr, data, sr)
    print(f"[ASR] Transcript complete ({time.time() - start_time:.1f}s).")
    segs = []
    for ch in result.get("chunks", []):
        start, end = ch["timestamp"]
        if start is None:
            start = 0.0
        if end is None:
            end = start + 1.0
        text = _clean(ch["text"])
        if text:
            segs.append({"start": float(start) + offset, "end": float(end) + offset, "text": text})
    # Phòng khi pipeline không trả chunks: dùng cả đoạn làm một segment
    if not segs and _clean(result.get("text", "")):
        segs.append({"start": offset, "end": offset + len(data) / sr, "text": _clean(result["text"])})
    return segs


def transcribe_segments(audio_path, model_size=None):
    """Trả [{'start','end','text'}] với mốc thời gian khớp file wav gốc (đã bù phần trim).
    Tự chọn bộ chạy: faster-whisper (máy có CTranslate2) hoặc transformers (máy không GPU)."""
    if config.ASR_BACKEND != "faster-whisper":
        return transcribe_segments_hf(audio_path, model_size)
    from asr.fast_runtime import transcribe_faster_segments

    model_size = model_size or config.ASR_MODEL_SIZE
    model_name = config.ASR_MODELS.get(model_size, config.ASR_MODELS["small"])
    asr = _load_pipeline(model_name)
    data, sr, offset = _prepare_audio(audio_path)
    print("[ASR] Transcribing audio (segments)...")
    segs = transcribe_faster_segments(asr, data)
    for s in segs:
        s["start"] += offset
        s["end"] += offset
    return segs