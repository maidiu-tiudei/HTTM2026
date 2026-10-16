"""Ghi âm trực tiếp từ microphone (Người A)."""
import wave
import numpy as np

import config


def record_from_mic(output_wav_path):
    """Ghi âm tới khi người dùng nhấn Enter lần 2. Trả về (đường dẫn wav, độ dài giây)."""
    import sounddevice as sd

    frames = []

    def callback(indata, frame_count, time_info, status):
        if status:
            print(f"[cảnh báo audio] {status}")
        frames.append(indata.copy())

    input("Nhấn Enter để BẮT ĐẦU ghi âm cuộc họp...")
    print("🔴 Đang ghi âm... nhấn Enter để DỪNG lại.")

    stream = sd.InputStream(
        samplerate=config.SAMPLE_RATE, channels=config.CHANNELS, dtype="int16", callback=callback
    )
    stream.start()
    input()
    stream.stop()
    stream.close()

    if not frames:
        raise RuntimeError("Không ghi được audio nào — kiểm tra lại thiết bị mic.")

    audio_data = np.concatenate(frames, axis=0)
    duration = len(audio_data) / config.SAMPLE_RATE
    print(f"⏹  Đã dừng ghi âm. Độ dài: {duration:.1f} giây")

    with wave.open(output_wav_path, "wb") as wf:
        wf.setnchannels(config.CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(config.SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())

    return output_wav_path, duration
