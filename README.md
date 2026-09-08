# HTTM2026
1. Tổng quan hệ thống

Luồng xử lý chính:

Người dùng
   │  upload / ghi âm
   ▼
Frontend (React / Streamlit)
   │  gọi API
   ▼
Backend API (FastAPI)
   │  đẩy job vào hàng đợi
   ▼
Queue / Job xử lý bất đồng bộ
   │
   ├──► Module ASR (Speech-to-Text)   → transcript
   │
   └──► Module NLP (Tóm tắt)          → summary + action items
   │
   ▼
Database (lưu transcript / summary)
   │
   ▼
Frontend hiển thị kết quả cho người dùng
