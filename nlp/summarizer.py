"""Tạo và kiểm tra biên bản bằng Gemini (ưu tiên) hoặc OpenAI."""
import json
import time

import config
from nlp.errors import SummaryError, classify_summary_error
from nlp.prompts import build_prompt
from nlp.schema import validate_summary


def summarize_with_openai(transcript, api_key, model=None):
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model or getattr(config, "OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": build_prompt(transcript)}],
            response_format={"type": "json_object"}, temperature=0.2,
        )
        text = response.choices[0].message.content
        if not text:
            raise SummaryError("invalid_response")
        return validate_summary(json.loads(text))
    except Exception as exc:
        raise classify_summary_error(exc) from None
    finally:
        client.close()
        print(f"[OpenAI] Request time: {time.perf_counter() - start:.2f}s")


def summarize_with_gemini(transcript, api_key, model=None, max_retries=None):
    return generate_gemini_json(build_prompt(transcript), api_key, validate_summary, model=model)


def generate_gemini_json(prompt, api_key, validate, *, model=None, system_instruction=None, max_output_tokens=2048):
    from google import genai
    from google.genai import types

    models = [model] if model else config.GEMINI_MODELS
    if not models:
        raise SummaryError("configuration")
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=20000, retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    last_error = SummaryError("unknown")
    try:
        for model_name in models:
            start = time.perf_counter()
            try:
                print(f"[Gemini] Processing: {model_name}")
                response = client.models.generate_content(
                    model=model_name, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        system_instruction=system_instruction,
                        thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                        max_output_tokens=max_output_tokens,
                    ),
                )
                if not response.text:
                    raise SummaryError("invalid_response")
                result = validate(json.loads(response.text))
                print(f"[Gemini] Success: {model_name} - {time.perf_counter() - start:.2f}s")
                return result
            except Exception as exc:
                last_error = classify_summary_error(exc)
                print(f"[Gemini] {model_name}: {last_error.code} after {time.perf_counter() - start:.2f}s")
                if last_error.code == "invalid_key":
                    break
        raise last_error
    finally:
        client.close()


def summarize_transcript(transcript):
    gemini_key, openai_key = config.get_api_keys()
    if gemini_key:
        return summarize_with_gemini(transcript, gemini_key)
    if openai_key:
        return summarize_with_openai(transcript, openai_key)
    raise SummaryError("missing_key")
