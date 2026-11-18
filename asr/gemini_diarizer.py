"""Tách người nói bằng Gemini nghe trực tiếp audio."""
import json
import re

import config

PROMPT = """Nghe file ghi âm cuộc hội thoại tiếng Việt này. Hãy chép lại nội dung và phân biệt từng người nói theo GIỌNG NÓI (cao độ, âm sắc, giới tính, cách nói) và ngữ cảnh hỏi đáp.
Quy tắc:
- Đánh số người nói theo thứ tự xuất hiện: 1, 2, 3...
- Mỗi lần đổi người nói là một mục mới. Người nói liên tiếp thì gộp thành một mục.
- Chép đúng lời nói, thêm dấu câu hợp lý, không bịa thêm nội dung.
Chỉ trả về JSON, dạng: [{"speaker": 1, "text": "..."}, {"speaker": 2, "text": "..."}]"""


def diarize_gemini(wav_path):
    gemini_key, _ = config.get_api_keys()
    if not gemini_key:
        raise RuntimeError("Thiếu GEMINI_API_KEY")
    from google import genai
    from google.genai import types

    with open(wav_path, "rb") as f:
        audio = f.read()
    if len(audio) > 18 * 1024 * 1024:
        raise RuntimeError("File quá dài để gửi trực tiếp cho Gemini")

    client = genai.Client(api_key=gemini_key, http_options=types.HttpOptions(timeout=120000))
    last = None
    try:
        for model in config.GEMINI_MODELS:
            try:
                r = client.models.generate_content(
                    model=model,
                    contents=[PROMPT, types.Part.from_bytes(data=audio, mime_type="audio/wav")],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", max_output_tokens=8192),
                )
                text = re.sub(r"^```(?:json)?|```$", "", (r.text or "").strip()).strip()
                segs = []
                for it in json.loads(text):
                    t = str(it.get("text", "")).strip()
                    if t:
                        segs.append({"start": None, "end": None, "text": t,
                                     "speaker": f"Người {int(it.get('speaker', 1))}"})
                if segs:
                    return segs
                last = RuntimeError("Gemini không trả nội dung")
            except Exception as exc:
                last = exc
        raise last or RuntimeError("Gemini lỗi")
    finally:
        client.close()