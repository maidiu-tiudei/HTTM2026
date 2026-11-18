"""Hỏi đáp nội dung cuộc họp bằng Gemini (ưu tiên) hoặc OpenAI."""
import json
import time

import config
from nlp.errors import SummaryError, classify_summary_error

CHAT_SYSTEM_PROMPT = """Bạn là trợ lý phân tích biên bản cuộc họp TinaMeetNote.
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng dựa trên Transcript (nội dung ghi âm đã phiên âm) và Biên bản tóm tắt của cuộc họp được cung cấp.

Quy tắc bắt buộc:
1. Chỉ sử dụng thông tin có trong Transcript và Biên bản cuộc họp. Tuyệt đối không tự suy diễn hoặc bịa đặt thông tin bên ngoài.
2. Nếu nội dung cuộc họp không đề cập đến vấn đề được hỏi, hãy trả lời rõ ràng: "Nội dung cuộc họp không đề cập đến thông tin này."
3. Nếu transcript có nhãn người nói (ví dụ [Người 1], [Người 2]), hãy nêu rõ ai là người phát biểu khi trả lời.
4. Trả lời bằng tiếng Việt tự nhiên, ngắn gọn, đi thẳng vào trọng tâm (có thể dùng gạch đầu dòng nếu liệt kê nhiều ý)."""


def _build_context(meeting: dict) -> str:
    transcript = (
        meeting.get("transcript_edited")
        or meeting.get("transcript_clean")
        or meeting.get("transcript")
        or ""
    ).strip()
    parts = [f"Tiêu đề cuộc họp: {meeting.get('title', 'Không rõ')}"]
    summary = meeting.get("summary")
    if isinstance(summary, dict) and summary:
        parts.append(f"Biên bản tóm tắt (JSON):\n{json.dumps(summary, ensure_ascii=False)}")
    parts.append(f"Nội dung chi tiết (Transcript):\n{transcript}")
    return "\n\n".join(parts)


def _format_history(history: list[dict]) -> str:
    lines = []
    for turn in history[-8:]:
        role = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        content = str(turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _chat_with_gemini(context: str, question: str, history: list[dict], api_key: str) -> str:
    from google import genai
    from google.genai import types

    models = getattr(config, "GEMINI_MODELS", None) or ["gemini-2.5-flash"]
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=20000, retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    history_text = _format_history(history)
    user_prompt = f"=== DỮ LIỆU CUỘC HỌP ===\n{context}\n\n"
    if history_text:
        user_prompt += f"=== LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ ===\n{history_text}\n\n"
    user_prompt += f"=== CÂU HỎI HIỆN TẠI ===\n{question}"

    last_error = SummaryError("unknown")
    try:
        for model_name in models:
            start = time.perf_counter()
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=CHAT_SYSTEM_PROMPT,
                        thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                        temperature=0.2,
                        max_output_tokens=1024,
                    ),
                )
                if not response.text:
                    raise SummaryError("invalid_response")
                print(f"[Gemini Chat] {model_name} - {time.perf_counter() - start:.2f}s")
                return response.text.strip()
            except Exception as exc:
                last_error = classify_summary_error(exc)
                print(f"[Gemini Chat] {model_name} failed: {last_error.code}")
                if last_error.code == "invalid_key":
                    break
        raise last_error
    finally:
        client.close()


def _chat_with_openai(context: str, question: str, history: list[dict], api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Dữ liệu cuộc họp:\n\n{context}"},
    ]
    for turn in history[-8:]:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=getattr(config, "OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
        )
        text = response.choices[0].message.content
        if not text:
            raise SummaryError("invalid_response")
        return text.strip()
    except Exception as exc:
        raise classify_summary_error(exc) from None
    finally:
        client.close()


def answer_meeting_question(meeting: dict, question: str, history: list[dict] | None = None) -> str:
    context = _build_context(meeting)
    history = history or []
    gemini_key, openai_key = config.get_api_keys()
    if gemini_key:
        return _chat_with_gemini(context, question, history, gemini_key)
    if openai_key:
        return _chat_with_openai(context, question, history, openai_key)
    raise SummaryError("missing_key")