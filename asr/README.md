# PhoWhisper với hai bộ thực thi

Hệ thống giữ cùng model VinAI PhoWhisper. Có thể chọn Transformers/PyTorch hoặc faster-whisper/CTranslate2. Gemini và định dạng transcript không thay đổi.

Trên máy Legion, mặc định hiện là `faster-whisper`, `PhoWhisper-large`, thiết bị tự chọn CUDA và kiểu tính toán `int8_float16`. Bản PyTorch CPU cũ vẫn được giữ để chuyển lại khi cần.

## Cài bộ thực thi nhanh trên Windows

```powershell
py -3.10 -m pip install -r requirements-asr-fast.txt
py -3.10 -m scripts.prepare_asr_ct2
```

Script chuyển đổi chỉ đọc trọng số VinAI đã có trong cache Hugging Face. Nếu chưa tải model, cần chạy model bằng bộ Transformers trước. Script không tự dùng model Whisper khác, không ghi đè thư mục model đã tồn tại và không tự tải mã Python từ model.

Kết quả chuyển đổi nằm trong `models/ct2/PhoWhisper-large-int8/`. File `source.json` ghi tên model và revision gốc để kiểm tra nguồn trọng số. Thư mục model không được commit lên Git.

## Chọn cách chạy

`ASR_MODEL_SIZE` trong `config.py` chọn kích thước model. `ASR_BACKEND` chọn bộ thực thi. Cần khởi động lại backend khi đổi các giá trị này.

Chạy nhanh với model đã chuyển:

```powershell
$env:ASR_BACKEND = 'faster-whisper'
.\run-backend.bat
```

Dùng lại bộ Transformers:

```powershell
$env:ASR_BACKEND = 'transformers'
.\run-backend.bat
```

Có thể cấu hình các biến này trong `.env`. Biến đã đặt ở PowerShell có ưu tiên cao hơn giá trị trong `.env`.

- `ASR_DEVICE=auto`: CTranslate2 tự chọn CUDA khi có GPU, nếu không thì CPU.
- `ASR_DEVICE=cuda`: yêu cầu GPU; không tự chuyển sang CPU khi gặp lỗi.
- `ASR_DEVICE=cpu`: dùng CPU.
- `ASR_COMPUTE_TYPE=auto`: CUDA dùng `int8_float16`, CPU dùng `int8`.

DLL NVIDIA được tìm trong các gói Python và thêm vào đường dẫn của riêng tiến trình backend. Không sửa PATH toàn hệ thống, không thay driver và không cần PyTorch CUDA để chạy CTranslate2.

Các phiên bản thư viện trong `requirements-asr-fast.txt` đã chọn cho RTX 3050 4 GB với driver 546.30. Máy khác cần kiểm tra lại tính tương thích. Chế độ GPU dùng một luồng nhận diện, không dùng batch lớn và chưa bật VAD để hạn chế bộ nhớ, tránh bỏ đoạn nói nhỏ.

## Đo trên cùng audio

Chạy mỗi bộ thực thi trong tiến trình riêng để không giữ hai model lớn trong RAM:

```powershell
py -3.10 -m scripts.benchmark_asr meeting_outputs/uploads/TEN_FILE.wav --backend transformers --runs 2 --output meeting_outputs/asr_benchmarks/transformers.json
py -3.10 -m scripts.benchmark_asr meeting_outputs/uploads/TEN_FILE.wav --backend faster-whisper --runs 2 --output meeting_outputs/asr_benchmarks/faster-whisper.json
```

File kết quả lưu thời lượng audio, thời gian nạp model, từng lần phiên âm và transcript. Không gọi Gemini hoặc cập nhật cuộc họp. Lần phiên âm đầu có thể gồm khởi tạo thư viện xử lý audio; dùng các lượt sau để so sánh tốc độ khi đã sẵn sàng.

Đã đo cùng audio 11,82 giây trên máy Legion, lấy lượt thứ hai sau khi model đã nạp: Transformers/PyTorch CPU 103,155 giây, CTranslate2 GPU INT8/FP16 7,051 giây (khoảng 14,63 lần). Đây là số liệu một mẫu, không phải cam kết cho mọi file. Dữ liệu chi tiết và transcript nằm trong `meeting_outputs/asr_benchmarks/` trên máy này.

INT8 và khác biệt giải mã có thể làm transcript thay đổi. Cần đối chiếu tên riêng, số liệu, phủ định, người phụ trách và thời hạn với audio gốc. So sánh hai transcript chưa phải đo WER khi chưa có bản chép tay làm chuẩn.

Trên trang chi tiết, cuộc họp mới sẽ ghi tên model, bộ thực thi, thiết bị và kiểu tính toán thực tế. Cuộc họp cũ chưa có thông tin này vẫn xem được bình thường.

Tài liệu gốc:
- https://github.com/SYSTRAN/faster-whisper
- https://opennmt.net/CTranslate2/guides/transformers.html
- https://github.com/VinAIResearch/PhoWhisper
