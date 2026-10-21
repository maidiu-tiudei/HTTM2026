"""Prompt + JSON schema cho biên bản họp (Người B). Sửa prompt ở đây để cải thiện chất lượng tóm tắt."""
from datetime import datetime

SUMMARY_PROMPT_TEMPLATE = """Bạn là trợ lý AI chuyên tạo biên bản họp tiếng Việt chuyên nghiệp.
Dưới đây là transcript thô (có thể có lỗi chính tả nhỏ do ASR) của một cuộc họp.
Hãy đọc kỹ và trả về DUY NHẤT một JSON object theo đúng schema sau, không thêm giải thích, không thêm markdown code fence:

{{
  "metadata": {{
    "tieu_de": "Tiêu đề cuộc họp (tự suy luận từ nội dung)",
    "thoi_luong": "ước lượng thời lượng, ví dụ '15 phút'",
    "ngay_thuc_hien": "{today}",
    "thanh_phan_tham_du": ["tên người 1 (vai trò nếu suy luận được)", "..."]
  }},
  "tong_quan": "2-4 câu tóm tắt tổng quan toàn bộ cuộc họp",
  "noi_dung_thao_luan": [
    {{"chu_de": "Tên chủ đề", "chi_tiet": ["ý chính 1", "ý chính 2"]}}
  ],
  "quyet_dinh": ["quyết định đã thống nhất 1", "..."],
  "action_items": [
    {{"cong_viec": "mô tả việc cần làm", "nguoi_phu_trach": "tên hoặc 'Chưa rõ'", "deadline": "ngày/giờ hoặc 'Chưa rõ'", "uu_tien": "Cao/Trung bình/Thấp"}}
  ]
}}

QUY TẮC BẮT BUỘC:
- Không tự suy đoán thời lượng từ transcript; nếu không có dữ liệu hãy để "Chưa rõ".
- Chỉ ghi quyết định, người phụ trách, mốc thời gian thật sự được đề cập. Không tự thêm.
- Nếu transcript không đủ thông tin cho một trường nào đó, điền "Chưa rõ" thay vì bịa đặt.

TRANSCRIPT:
\"\"\"
{transcript}
\"\"\"
"""


def build_prompt(transcript):
    return SUMMARY_PROMPT_TEMPLATE.format(
        transcript=transcript, today=datetime.now().strftime("%d/%m/%Y")
    )
