# Meeting Notes AI — Hệ thống AI tự động ghi chú cuộc họp

Ghi âm (hoặc upload file) → Speech-to-Text (PhoWhisper) → Tóm tắt bằng LLM (Gemini) → Biên bản họp có cấu trúc.

## Cấu trúc & phân công

| Thư mục / file | Nội dung |
|---|---|---|
| `asr/recorder.py` | Ghi âm từ mic |
| `asr/transcriber.py` | PhoWhisper: audio → transcript | 
| `nlp/prompts.py` | Prompt + JSON schema biên bản |
| `nlp/summarizer.py` | Gọi Gemini/OpenAI | 
| `nlp/formatter.py` | JSON → biên bản văn bản | 
| `backend/`, `frontend/` | API, giao diện, database | 
| `config.py` | Cấu hình chung (model, sample rate...) |
| `main.py` | Chạy pipeline từ dòng lệnh |
| `docs/` | Slide, báo cáo, bảng so sánh ASR | 
| `data/samples/` | Audio / transcript mẫu để test |

## Cài đặt

```
pip install -r requirements.txt
copy .env.example .env      # rồi mở .env điền GEMINI_API_KEY
```

## Chạy

```
python main.py              # ghi âm từ mic (Enter để bắt đầu / dừng)
python main.py file.mp3     # dùng file audio có sẵn
```

Kết quả lưu trong `meeting_outputs/`.

## Quy ước làm việc với Git

- Mỗi người chỉ sửa trong thư mục của mình; muốn đổi `config.py` hoặc `main.py` thì báo cả nhóm.
- Không commit file `.env` (đã nằm trong `.gitignore`).
