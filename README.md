# TinaMeetNote — Hệ thống AI tự động ghi chú cuộc họp

Ứng dụng MVP tiếp nhận audio tiếng Việt, phiên âm bằng PhoWhisper, tạo biên bản bằng Gemini và lưu kết quả để xem lại.

## Các chức năng hiện có

- Tạo cuộc họp, tải audio hoặc ghi âm bằng microphone của trình duyệt.
- Chuẩn hóa audio về WAV 16 kHz, mono.
- Phiên âm bằng PhoWhisper-large với Transformers hoặc faster-whisper/CTranslate2.
- Tạo biên bản gồm tổng quan, chủ đề thảo luận, quyết định và công việc.
- Lưu transcript ngay sau ASR, độc lập với bước tạo biên bản.
- Sửa transcript trong bản riêng, giữ nguyên bản ASR gốc.
- Tạo lại biên bản từ transcript đã lưu hoặc đã chỉnh, không chạy lại ASR.
- Giữ biên bản cũ khi lần tạo lại thất bại.
- Hiển thị giai đoạn, thời gian xử lý và bộ thực thi ASR thực tế.

Hiện chưa có phân tách người nói, đăng nhập/phân quyền hoặc xuất Word/PDF. AI có thể nhận diện và tổng hợp sai; cần đối chiếu tên riêng, số liệu và công việc với audio gốc.

## Cài đặt trên Windows với Python 3.10

Tại thư mục gốc dự án:

```powershell
py -3.10 -m pip install -r requirements.txt
```

Tạo file `.env` theo `.env.example` rồi điền `GEMINI_API_KEY`. Key chỉ được backend sử dụng. Transcript được gửi đến Gemini qua API; audio được xử lý bằng PhoWhisper trên máy.

### Chuẩn bị bộ thực thi ASR

Mặc định trong `config.py` là PhoWhisper-large với faster-whisper. Model đã chuyển không đi kèm mã nguồn Git.

Trên Windows dùng GPU NVIDIA, cài thêm thư viện GPU:

```powershell
py -3.10 -m pip install -r requirements-asr-fast.txt
```

Nếu máy chưa có trọng số PhoWhisper-large trong cache, tải từ VinAI (khoảng 6 GB):

```powershell
py -3.10 -c "from huggingface_hub import snapshot_download; snapshot_download('vinai/PhoWhisper-large')"
```

Sau đó chuyển model trong cache sang CTranslate2:

```powershell
py -3.10 -m scripts.prepare_asr_ct2
```

Model chuyển đổi được lưu trong `models/ct2/`, kèm tên và revision nguồn. Script không tự thay bằng một model Whisper khác.

Các thư viện NVIDIA đã được thử trên RTX 3050 Laptop 4 GB, driver 546.30. Máy khác cần kiểm tra lại tính tương thích. Máy không có CUDA sẽ dùng CTranslate2 CPU INT8 khi để `ASR_DEVICE=auto`.

Để dùng lại Transformers mà chưa cần chuyển đổi, đặt `ASR_BACKEND=transformers` trong `.env` hoặc PowerShell:

```powershell
$env:ASR_BACKEND = 'transformers'
```

Chi tiết cài đặt, chuyển đổi và đo hiệu năng: [asr/README.md](asr/README.md).

## Chạy giao diện web

Mở hai cửa sổ PowerShell tại thư mục gốc.

Backend:

```powershell
.\run-backend.bat
```

Hoặc:

```powershell
py -3.10 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
py -3.10 -m http.server 5500 --bind 127.0.0.1 -d frontend
```

- Giao diện: http://127.0.0.1:5500/index.html
- API: http://127.0.0.1:8000/docs

Đợi model sẵn sàng trong terminal trước khi demo. Khi cập nhật giao diện, nhấn Ctrl + F5. Cần khởi động lại backend khi thay cấu hình ASR hoặc API key.

## Luồng xử lý và lưu trữ

Frontend gửi audio tới FastAPI. Backend chuẩn hóa file, chạy PhoWhisper rồi lưu transcript. Tiếp đó Gemini tạo biên bản JSON; backend kiểm tra cấu trúc và lưu JSON/TXT. Frontend lấy trạng thái định kỳ để hiển thị kết quả.

Dữ liệu nằm trong `meeting_outputs/` và không được commit:
- `uploads/`: audio đầu vào và WAV.
- `meetings.json`: thông tin cuộc họp, transcript, biên bản, trạng thái và thời gian.
- `transcript_*.txt`, `bienban_*.json`, `bienban_*.txt`: kết quả xử lý.

Tác vụ nền chạy trong tiến trình FastAPI, chưa có hàng đợi tác vụ bền vững. Nếu dừng backend khi đang xử lý, tác vụ không tự tiếp tục sau khi khởi động lại. Phiên bản hiện phục vụ thử nghiệm cục bộ.

## Kiểm thử

```powershell
py -3.10 -m unittest discover -s tests -v
```

Bộ kiểm thử dùng dữ liệu tạm và AI giả lập, không gọi Gemini hoặc tải model. Phép đo ASR thật có thể chạy riêng bằng `scripts.benchmark_asr`; xem hướng dẫn trong thư mục `asr`.

## Cấu trúc mã nguồn

| Đường dẫn | Vai trò |
|---|---|
| `asr/transcriber.py` | Chuẩn hóa dữ liệu và chọn bộ thực thi ASR |
| `asr/fast_runtime.py` | Nạp PhoWhisper CTranslate2 và thư viện GPU |
| `scripts/prepare_asr_ct2.py` | Chuyển model từ cache |
| `scripts/benchmark_asr.py` | Đo ASR cục bộ |
| `nlp/prompts.py` | Prompt tạo biên bản |
| `nlp/schema.py`, `nlp/errors.py` | Kiểm tra kết quả và phân loại lỗi |
| `backend/` | API, pipeline và lưu trữ |
| `frontend/` | Giao diện HTML/CSS/JavaScript |
| `tests/` | Kiểm thử ASR, API và phục hồi dữ liệu |

## Quy ước Git

Không commit `.env`, API key, dữ liệu cuộc họp, model, audio thử nghiệm hoặc `__pycache__`. Giữ dữ liệu cuộc họp và cấu hình riêng trên từng máy.
