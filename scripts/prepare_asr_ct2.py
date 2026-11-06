"""Chuyển PhoWhisper đã có trong cache sang CTranslate2; không tải model khác."""
import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import config
from asr.fast_runtime import converted_model_path


def prepare(model_size=None):
    from huggingface_hub import snapshot_download
    from ctranslate2.converters import TransformersConverter

    size = model_size or config.ASR_MODEL_SIZE
    if size not in config.ASR_MODELS:
        raise ValueError("Kích thước model không hợp lệ")
    model_name = config.ASR_MODELS[size]
    destination = converted_model_path(model_name)
    if destination.exists():
        manifest = destination / "source.json"
        if (destination / "model.bin").is_file() and manifest.is_file():
            info = json.loads(manifest.read_text(encoding="utf-8"))
            if info.get("source_model") == model_name:
                print(f"[ASR] Converted model already available: {destination}")
                return destination
        raise RuntimeError("Thư mục đích đã tồn tại nhưng không hợp lệ. Không tự ghi đè model.")

    source = Path(snapshot_download(model_name, local_files_only=True))
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"[ASR] Source: {model_name} @ {source.name}", flush=True)
    print("[ASR] Converting cached weights to int8_float16; this can take several minutes.", flush=True)
    with tempfile.TemporaryDirectory(prefix=".ct2-build-", dir=destination.parent) as build:
        # TemporaryDirectory chỉ xóa thư mục riêng vừa tạo trong models/ct2.
        build_path = Path(build).resolve()
        if not build_path.is_relative_to(destination.parent.resolve()):
            raise RuntimeError("Thư mục chuyển đổi nằm ngoài đường dẫn cho phép")
        output = build_path / "model"
        converter = TransformersConverter(
            str(source), copy_files=["tokenizer.json", "preprocessor_config.json"],
            load_as_float16=True,
        )
        converter.convert(str(output), quantization="int8_float16")
        if not (output / "tokenizer.json").is_file():
            raise RuntimeError("Thiếu tokenizer.json sau chuyển đổi")
        (output / "source.json").write_text(json.dumps({
            "source_model": model_name, "source_revision": source.name,
            "quantization": "int8_float16", "converted_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        output.rename(destination)
    print(f"[ASR] Converted model saved: {destination}", flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-size", choices=list(config.ASR_MODELS), default=config.ASR_MODEL_SIZE)
    args = parser.parse_args()
    prepare(args.model_size)
