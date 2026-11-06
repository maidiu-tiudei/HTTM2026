"""Đo ASR cục bộ; không gọi Gemini, không sửa dữ liệu cuộc họp."""
import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import soundfile as sf

import config
from asr.transcriber import _load_pipeline, get_asr_runtime, transcribe_audio
from backend.pipeline import to_wav


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--backend", choices=["transformers", "faster-whisper"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    if not args.audio.is_file() or args.runs < 1:
        parser.error("Cần file audio tồn tại và runs >= 1")
    if args.output.exists():
        parser.error("File kết quả đã tồn tại; chọn tên mới để tránh ghi đè")
    config.ASR_BACKEND = args.backend
    os.environ["HF_HUB_OFFLINE"] = "1"
    model_name = config.ASR_MODELS[config.ASR_MODEL_SIZE]
    started = time.perf_counter()
    _load_pipeline(model_name)
    load_seconds = time.perf_counter() - started
    measurements = []
    with tempfile.TemporaryDirectory(prefix="tinameet-asr-") as temporary:
        wav = Path(temporary) / "audio.wav"
        to_wav(args.audio, wav)
        duration = sf.info(wav).duration
        for index in range(args.runs):
            started = time.perf_counter()
            text = transcribe_audio(str(wav))
            seconds = time.perf_counter() - started
            measurements.append({"run": index + 1, "asr_seconds": round(seconds, 3),
                                 "real_time_factor": round(seconds / duration, 3) if duration else None,
                                 "transcript": text})
            print(f"[Benchmark] Run {index + 1}: {seconds:.3f}s", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"audio": str(args.audio.resolve()), "audio_seconds": duration,
                                      "runtime": get_asr_runtime(), "load_seconds": round(load_seconds, 3),
                                      "measurements": measurements}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Benchmark] Saved: {args.output}", flush=True)


if __name__ == "__main__":
    main()
