"""Bộ thực thi CTranslate2 cho đúng trọng số PhoWhisper đã chuyển trên máy."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import config

_dll_handles = []
_dll_paths = set()


def configure_nvidia_libraries():
    """Chỉ thêm đường dẫn DLL cho tiến trình hiện tại, không sửa PATH Windows."""
    if sys.platform != "win32":
        return
    for module in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            spec = importlib.util.find_spec(module)
        except (ModuleNotFoundError, ValueError):
            continue
        if spec is None:
            continue
        for root in spec.submodule_search_locations or []:
            directory = str(Path(root) / "bin")
            if Path(directory).is_dir() and directory not in _dll_paths:
                _dll_handles.append(os.add_dll_directory(directory))
                os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
                _dll_paths.add(directory)


def converted_model_path(model_name):
    name = model_name.split("/")[-1]
    return Path(config.ASR_CT2_MODEL_DIR) / (name + "-int8")


def load_faster_model(model_name):
    configure_nvidia_libraries()
    try:
        import ctranslate2
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Chưa có bộ thực thi nhanh. Chạy: py -3.10 -m pip install -r requirements-asr-fast.txt") from exc

    directory = converted_model_path(model_name)
    manifest_file = directory / "source.json"
    if not (directory / "model.bin").is_file() or not manifest_file.is_file():
        raise RuntimeError("Chưa chuyển model PhoWhisper. Chạy: py -3.10 -m scripts.prepare_asr_ct2")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("source_model") != model_name:
        raise RuntimeError("Model CTranslate2 không khớp model PhoWhisper đang cấu hình.")

    device = config.ASR_DEVICE
    if device not in ("auto", "cuda", "cpu"):
        raise RuntimeError("ASR_DEVICE chỉ nhận auto, cuda hoặc cpu.")
    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    compute = config.ASR_COMPUTE_TYPE
    if compute == "auto":
        compute = "int8_float16" if device == "cuda" else "int8"
    try:
        supported = ctranslate2.get_supported_compute_types(device)
        if compute not in supported:
            raise RuntimeError(f"Thiết bị {device} không hỗ trợ compute_type={compute}.")
        model = WhisperModel(str(directory), device=device, compute_type=compute,
                             num_workers=1, local_files_only=True)
    except Exception as exc:
        raise RuntimeError(
            f"Không nạp được PhoWhisper CTranslate2 ({device}/{compute}). "
            "Kiểm tra DLL NVIDIA và VRAM; đặt ASR_BACKEND=transformers để dùng lại bộ cũ. "
            f"Chi tiết: {exc}"
        ) from exc
    info = {"backend": "faster-whisper", "model": model_name, "device": device,
            "compute_type": compute, "source_revision": manifest.get("source_revision")}
    print(f"[ASR] faster-whisper | {model_name} | {device} | {compute}")
    return model, info


def transcribe_faster(model, data):
    # Không bật VAD hoặc chia batch: tránh bỏ đoạn nói nhỏ và tiết kiệm VRAM 4 GB.
    segments, _ = model.transcribe(
        data, language="vi", task="transcribe", beam_size=config.ASR_BEAM_SIZE,
        temperature=0.0, vad_filter=False, condition_on_previous_text=True,
        no_repeat_ngram_size=3, repetition_penalty=1.3,
    )
    # segments là generator; phải duyệt hết mới đo đủ thời gian và nhận đủ transcript.
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def transcribe_faster_segments(model, data):
    """Giống transcribe_faster nhưng trả [{'start','end','text'}] (giây, tính từ đầu `data`)."""
    segments, _ = model.transcribe(
        data, language="vi", task="transcribe", beam_size=config.ASR_BEAM_SIZE,
        temperature=0.0, vad_filter=False, condition_on_previous_text=True,
        no_repeat_ngram_size=3, repetition_penalty=1.3,
    )
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments if s.text.strip()]