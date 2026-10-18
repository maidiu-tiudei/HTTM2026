import sys
from pathlib import Path

# Cho phép import config, asr, nlp từ thư mục gốc dự án
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))