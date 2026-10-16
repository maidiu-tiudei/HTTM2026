"""Speech-to-Text bằng PhoWhisper (Người A)."""
import time
from functools import lru_cache

import numpy as np

import config


@lru_cache(maxsize=2)
def _load_pipeline(model_name):
    """Chỉ tải model 1 lần cho mỗi tiến trình (quan trọng khi chạy backend: không tải lại mỗi request)."""
    from transformers import pipeline
    print(f"Đang tải model '{model_name}' (lần đầu sẽ hơi lâu)...")
    return pipeline("automatic-speech-recognition", model=model_name)


def transcribe_audio(audio_path, model_size=None):
    """Chuyển file audio (wav/mp3...) thành văn bản."""
    import soundfile as sf
    import librosa

    model_size = model_size or config.ASR_MODEL_SIZE
    model_name = config.ASR_MODELS.get(model_size, config.ASR_MODELS["small"])
    asr = _load_pipeline(model_name)

    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)

    # Resample về 16kHz bằng librosa (không phụ thuộc torchaudio)
    if sr != config.SAMPLE_RATE:
        data = librosa.resample(data, orig_sr=sr, target_sr=config.SAMPLE_RATE)
        sr = config.SAMPLE_RATE

    # Cắt khoảng lặng đầu/cuối: nguyên nhân phổ biến gây lặp từ (hallucination)
    data, _ = librosa.effects.trim(data, top_db=30)
    duration = len(data) / sr

    print("Đang chuyển giọng nói thành văn bản...")
    start = time.time()
    generate_kwargs = {"no_repeat_ngram_size": 3, "repetition_penalty": 1.3}

    if duration <= 30:
        result = asr({"array": data, "sampling_rate": sr}, generate_kwargs=generate_kwargs)
    else:
        result = asr(
            {"array": data, "sampling_rate": sr},
            return_timestamps=True,
            generate_kwargs=generate_kwargs,
        )

    print(f"Xong transcript ({time.time() - start:.1f}s).")
    return result["text"].strip()
