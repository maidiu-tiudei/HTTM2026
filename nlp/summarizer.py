"""Tóm tắt transcript bằng LLM API: Gemini (mặc định) hoặc OpenAI (Người B)."""
import json
import time

import config
from nlp.prompts import build_prompt


def summarize_with_openai(transcript, api_key, model=None):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model or config.OPENAI_MODEL,
        messages=[{"role": "user", "content": build_prompt(transcript)}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)


def summarize_with_gemini(transcript, api_key, model=None, max_retries=None):
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError, ClientError

    max_retries = max_retries or config.MAX_RETRIES
    client = genai.Client(api_key=api_key)
    prompt = build_prompt(transcript)
    candidates = [model] if model else config.GEMINI_MODELS

    last_error = None
    for candidate_model in candidates:
        for attempt in range(1, max_retries + 1):
            try:
                resp = client.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", temperature=0.2
                    ),
                )
                if candidate_model != candidates[0]:
                    print(f"(Đã dùng model dự phòng: {candidate_model})")
                return json.loads(resp.text)
            except ServerError as e:
                last_error = e
                if "UNAVAILABLE" in str(e) or "503" in str(e):
                    wait = attempt * 10
                    print(f"⚠️  '{candidate_model}' đang quá tải (lần {attempt}/{max_retries}). Đợi {wait}s...")
                    time.sleep(wait)
                else:
                    break
            except ClientError as e:
                if "NOT_FOUND" in str(e) or "404" in str(e):
                    print(f"⚠️  Model '{candidate_model}' không còn khả dụng, thử model khác...")
                    last_error = e
                    break
                raise

    raise RuntimeError(
        f"Không tóm tắt được với bất kỳ model nào trong {candidates}. Lỗi cuối: {last_error}\n"
        "Kiểm tra tên model mới nhất tại https://ai.google.dev/gemini-api/docs/models "
        "rồi sửa GEMINI_MODELS trong config.py."
    )


def summarize_transcript(transcript):
    """Tự chọn Gemini hoặc OpenAI tùy key nào có trong .env. Trả None nếu chưa có key."""
    gemini_key, openai_key = config.get_api_keys()

    if gemini_key:
        print("Đang tóm tắt bằng Gemini...")
        return summarize_with_gemini(transcript, gemini_key)
    if openai_key:
        print("Đang tóm tắt bằng OpenAI...")
        return summarize_with_openai(transcript, openai_key)

    print("\n⚠️  Chưa có GEMINI_API_KEY hoặc OPENAI_API_KEY trong file .env — bỏ qua bước tóm tắt.\n")
    return None
