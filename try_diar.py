import config
config.ASR_MODEL_SIZE = "small"

from asr.transcriber import transcribe_segments_hf
from asr.diarizer import diarize, assign_speakers, format_transcript

wav = r"meeting_outputs\uploads\541d7afe.wav"
segs = transcribe_segments_hf(wav)
print("ASR xong:", len(segs), "đoạn")
segs = assign_speakers(segs, diarize(wav))
print(format_transcript(segs))
