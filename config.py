"""Cấu hình chung của dự án. Sửa ở đây thay vì sửa rải rác trong code."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # đọc GEMINI_API_KEY / OPENAI_API_KEY từ file .env
except ImportError:
    pass

# ---- Ghi âm / ASR (Người A) ----
SAMPLE_RATE = 16000          # PhoWhisper cần 16kHz mono
CHANNELS = 1
ASR_MODEL_SIZE = "small"     # tiny / base / small / medium / large
ASR_MODELS = {
    "tiny": "vinai/PhoWhisper-tiny",
    "base": "vinai/PhoWhisper-base",
    "small": "vinai/PhoWhisper-small",
    "medium": "vinai/PhoWhisper-medium",
    "large": "vinai/PhoWhisper-large",
}

# ---- Tóm tắt / NLP (Người B) ----
# Google đổi model khá nhanh: nếu báo 404 "model no longer available", sửa danh sách này.
GEMINI_MODELS = ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
OPENAI_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3

# ---- Đầu ra ----
OUTPUT_DIR = "meeting_outputs"

def get_api_keys():
    return os.environ.get("GEMINI_API_KEY"), os.environ.get("OPENAI_API_KEY")
