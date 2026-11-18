"""Tải hai model ONNX từ bản phát hành chính thức của sherpa-onnx."""
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from asr.diarization import MODEL_DIR, SEGMENTATION, EMBEDDING

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
ARCHIVE = "sherpa-onnx-pyannote-segmentation-3-0"
EMBEDDING_ASSET = "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"


def download(url, output):
    with urlopen(url, timeout=60) as response, output.open("wb") as target:
        shutil.copyfileobj(response, target)


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL_DIR) as temporary:
        directory = Path(temporary)
        if not SEGMENTATION.is_file():
            archive = directory / "segmentation.tar.bz2"
            download(f"{RELEASES}/speaker-segmentation-models/{ARCHIVE}.tar.bz2", archive)
            with tarfile.open(archive, "r:bz2") as source:
                member = source.getmember(f"{ARCHIVE}/model.onnx")
                if not member.isfile():
                    raise RuntimeError("Tệp model ONNX không hợp lệ")
                with source.extractfile(member) as stream, (directory / "model.onnx").open("wb") as target:
                    shutil.copyfileobj(stream, target)
            (directory / "model.onnx").replace(SEGMENTATION)
        if not EMBEDDING.is_file():
            embedding = directory / "embedding.onnx"
            download(f"{RELEASES}/speaker-recongition-models/{EMBEDDING_ASSET}", embedding)
            embedding.replace(EMBEDDING)
    print("[Speakers] Model files ready.")


if __name__ == "__main__":
    main()
