"""Chuyển JSON tóm tắt thành biên bản họp dạng văn bản (Người B)."""


def format_bien_ban(data):
    meta = data.get("metadata", {})
    lines = [
        "BIÊN BẢN HỌP TỔNG HỢP TỰ ĐỘNG",
        "(Hệ thống AI Meeting Notes tự động ghi nhận)",
        "",
        "I. THÔNG TIN CHUNG (METADATA)",
        f"Tiêu đề cuộc họp: {meta.get('tieu_de', 'Chưa rõ')}",
        f"Thời lượng: {meta.get('thoi_luong', 'Chưa rõ')} | Ngày thực hiện: {meta.get('ngay_thuc_hien', 'Chưa rõ')}",
        "Thành phần tham dự:",
    ]
    for p in meta.get("thanh_phan_tham_du", []):
        lines.append(f"  - {p}")
    lines += [
        "Thư ký cuộc họp: Hệ thống AI Meeting Notes (Tự động trích xuất)",
        "",
        "II. TỔNG QUAN CUỘC HỌP (EXECUTIVE SUMMARY)",
        data.get("tong_quan", "Chưa rõ"),
        "",
        "III. NỘI DUNG THẢO LUẬN CHI TIẾT (NOTES & TOPICS)",
    ]
    for i, topic in enumerate(data.get("noi_dung_thao_luan", []), 1):
        lines.append(f"{i}. {topic.get('chu_de', '')}")
        for d in topic.get("chi_tiet", []):
            lines.append(f"   - {d}")

    lines += ["", "IV. CÁC QUYẾT ĐỊNH ĐÃ THỐNG NHẤT (KEY DECISIONS)"]
    for d in data.get("quyet_dinh", []):
        lines.append(f"  - {d}")

    lines += ["", "V. DANH SÁCH CÔNG VIỆC CẦN LÀM (ACTION ITEMS)"]
    items = data.get("action_items", [])
    if items:
        lines.append(f"{'STT':<5}{'Công việc':<45}{'Người phụ trách':<20}{'Deadline':<20}{'Ưu tiên':<10}")
        for i, it in enumerate(items, 1):
            lines.append(
                f"{i:<5}{it.get('cong_viec', '')[:43]:<45}{it.get('nguoi_phu_trach', '')[:18]:<20}"
                f"{it.get('deadline', '')[:18]:<20}{it.get('uu_tien', ''):<10}"
            )
    else:
        lines.append("  (Không có action item nào được xác định)")
    return "\n".join(lines)
