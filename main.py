"""
Chạy toàn bộ pipeline từ dòng lệnh (thay cho test_record.py).

    python main.py              # ghi âm từ mic
    python main.py file.mp3     # dùng file audio có sẵn
"""
import json
import os
import sys
from datetime import datetime

import config
from asr.recorder import record_from_mic
from asr.transcriber import transcribe_audio
from nlp.summarizer import summarize_transcript
from nlp.formatter import format_bien_ban


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = lambda name: os.path.join(config.OUTPUT_DIR, name)

    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        if not os.path.exists(audio_path):
            print(f"❌ Không tìm thấy file: {audio_path}")
            return
        print(f"Dùng file audio có sẵn: {audio_path}\n")
    else:
        audio_path = out(f"recording_{ts}.wav")
        record_from_mic(audio_path)
        print(f"Đã lưu file ghi âm: {audio_path}\n")

    transcript = transcribe_audio(audio_path)
    with open(out(f"transcript_{ts}.txt"), "w", encoding="utf-8") as f:
        f.write(transcript)
    print("\n--- TRANSCRIPT ---")
    print(transcript)

    summary = summarize_transcript(transcript)
    if summary is None:
        print("Kết thúc — chỉ có transcript, chưa có biên bản tóm tắt.")
        return

    with open(out(f"bienban_{ts}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    text = format_bien_ban(summary)
    with open(out(f"bienban_{ts}.txt"), "w", encoding="utf-8") as f:
        f.write(text)

    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)
    print(f"\nĐã lưu kết quả vào thư mục '{config.OUTPUT_DIR}/' (transcript_*.txt, bienban_*.json, bienban_*.txt)")


if __name__ == "__main__":
    main()
