"""Thông báo an toàn: không trả nguyên lỗi SDK có thể chứa API key ra web."""
import json
from .schema import SummaryValidationError

MESSAGES = {
    "missing_key": "Chưa cấu hình API key. Thêm GEMINI_API_KEY vào .env và khởi động lại backend.",
    "invalid_key": "API key không hợp lệ hoặc không có quyền gọi model. Kiểm tra key và quyền truy cập Gemini.",
    "rate_limit": "Dịch vụ AI đã đạt hạn mức yêu cầu hoặc quota. Kiểm tra hạn mức và thử lại sau.",
    "timeout": "Dịch vụ AI phản hồi quá thời gian chờ. Bạn có thể tạo lại biên bản sau.",
    "unavailable": "Dịch vụ AI đang quá tải hoặc tạm thời không khả dụng. Hãy thử lại sau.",
    "model_not_found": "Model AI đã cấu hình không khả dụng. Kiểm tra danh sách model trong config.py.",
    "invalid_response": "AI trả về biên bản thiếu trường, sai kiểu dữ liệu hoặc JSON không hợp lệ. Hãy thử tạo lại.",
    "configuration": "Cấu hình model hoặc yêu cầu AI chưa phù hợp. Kiểm tra cấu hình backend.",
    "storage_error": "Không lưu được biên bản mới. Kiểm tra quyền ghi và dung lượng ổ đĩa rồi thử lại.",
    "unknown": "Không tạo được biên bản do lỗi kết nối hoặc xử lý. Hãy thử lại sau.",
}


class SummaryError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES.get(code, MESSAGES["unknown"]))


def classify_summary_error(exc):
    if isinstance(exc, SummaryError):
        return exc
    if isinstance(exc, (json.JSONDecodeError, SummaryValidationError)):
        return SummaryError("invalid_response")
    code = str(getattr(exc, "code", None) or getattr(exc, "status_code", ""))
    detail = (type(exc).__name__ + " " + str(exc)).lower()
    if code in ("401", "403") or "api_key_invalid" in detail or "api key not valid" in detail:
        return SummaryError("invalid_key")
    if code == "429" or "resource_exhausted" in detail:
        return SummaryError("rate_limit")
    if code in ("408", "504") or "timeout" in detail or "deadline" in detail:
        return SummaryError("timeout")
    if code in ("500", "502", "503") or "unavailable" in detail:
        return SummaryError("unavailable")
    if code == "404":
        return SummaryError("model_not_found")
    if code == "400":
        return SummaryError("configuration")
    return SummaryError("unknown")
