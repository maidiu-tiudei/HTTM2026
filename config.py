"""Cấu hình chung của dự án. Sửa ở đây thay vì sửa rải rác trong code."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # đọc GEMINI_API_KEY / OPENAI_API_KEY từ file .env
except ImportError:
    pass

# ---- Ghi âm / ASR (Người A) ----
SAMPLE_RATE = 16000          # PhoWhisper cần 16kHz mono
CHANNELS = 1
ASR_MODEL_SIZE = "large"     # tiny / base / small / medium / large
ASR_MODELS = {
    "tiny": "vinai/PhoWhisper-tiny",
    "base": "vinai/PhoWhisper-base",
    "small": "vinai/PhoWhisper-small",
    "medium": "vinai/PhoWhisper-medium",
    "large": "vinai/PhoWhisper-large",
}

# Đổi ASR_BACKEND trong môi trường thành transformers để dùng lại bộ thực thi cũ.
# Model large đã được chuyển và kiểm thử trên RTX 3050 của máy Legion.
ASR_BACKEND = os.environ.get("ASR_BACKEND", "faster-whisper")
ASR_CT2_MODEL_DIR = Path(__file__).resolve().parent / "models" / "ct2"
ASR_DEVICE = os.environ.get("ASR_DEVICE", "auto")  # auto / cuda / cpu
ASR_COMPUTE_TYPE = os.environ.get("ASR_COMPUTE_TYPE", "auto")
ASR_BEAM_SIZE = 5

# ---- Tóm tắt / NLP (Người B) ----
# Google đổi model khá nhanh: nếu báo 404 "model no longer available", sửa danh sách này.
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite"
]

MAX_RETRIES = 1


# ---- Đầu ra ----
OUTPUT_DIR = "meeting_outputs"

def get_api_keys():
    return os.environ.get("GEMINI_API_KEY"), os.environ.get("OPENAI_API_KEY")
