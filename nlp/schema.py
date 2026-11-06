"""Kiểm tra biên bản trước khi định dạng hoặc lưu kết quả AI."""
from copy import deepcopy


class SummaryValidationError(ValueError):
    pass


def validate_summary(value):
    def fail(path):
        raise SummaryValidationError(f"Biên bản thiếu hoặc sai kiểu dữ liệu tại {path}")

    def obj(item, path):
        if not isinstance(item, dict):
            fail(path)
        return item

    def string(item, path):
        if not isinstance(item, str) or not item.strip():
            fail(path)

    def array(item, path):
        if not isinstance(item, list):
            fail(path)
        return item

    data = obj(value, "biên bản")
    meta = obj(data.get("metadata"), "metadata")
    for key in ("tieu_de", "thoi_luong", "ngay_thuc_hien"):
        string(meta.get(key), f"metadata.{key}")
    for person in array(meta.get("thanh_phan_tham_du"), "metadata.thanh_phan_tham_du"):
        string(person, "metadata.thanh_phan_tham_du[]")
    string(data.get("tong_quan"), "tong_quan")
    for topic in array(data.get("noi_dung_thao_luan"), "noi_dung_thao_luan"):
        obj(topic, "noi_dung_thao_luan[]")
        string(topic.get("chu_de"), "noi_dung_thao_luan[].chu_de")
        for detail in array(topic.get("chi_tiet"), "noi_dung_thao_luan[].chi_tiet"):
            string(detail, "noi_dung_thao_luan[].chi_tiet[]")
    for decision in array(data.get("quyet_dinh"), "quyet_dinh"):
        string(decision, "quyet_dinh[]")
    for task in array(data.get("action_items"), "action_items"):
        obj(task, "action_items[]")
        for key in ("cong_viec", "nguoi_phu_trach", "deadline", "uu_tien"):
            string(task.get(key), f"action_items[].{key}")
        if task["uu_tien"] not in ("Cao", "Trung bình", "Thấp", "Chưa rõ"):
            fail("action_items[].uu_tien")
    if data.get("transcript_chinh_sua") is not None:
        string(data["transcript_chinh_sua"], "transcript_chinh_sua")
    return deepcopy(data)
