# backend/ — Người C

Dự kiến: FastAPI nhận file audio, đẩy job xử lý bất đồng bộ, lưu kết quả vào database.

Có thể dùng lại trực tiếp code của A và B:

```python
from asr.transcriber import transcribe_audio      # audio -> transcript
from nlp.summarizer import summarize_transcript   # transcript -> dict biên bản (JSON schema trong nlp/prompts.py)
from nlp.formatter import format_bien_ban         # dict -> văn bản
```

Gợi ý endpoint: `POST /api/meetings` (upload audio), `GET /api/meetings/{id}` (xem trạng thái + kết quả).
Lưu ý: `transcribe_audio` đã cache model, nên không tải lại mỗi request.
