"""Phân tách người nói bằng pyannote rồi gán nhãn cho các đoạn ASR."""
import os
import re
from functools import lru_cache


@lru_cache(maxsize=1)
def _load():
    import torch
    from pyannote.audio import Pipeline

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("Thiếu HF_TOKEN trong .env để dùng nhận diện người nói")
    # pyannote 4.x dùng token=, bản 3.x dùng use_auth_token=
    try:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
    except TypeError:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    if torch.cuda.is_available():
        pipe.to(torch.device("cuda"))
    return _tune(pipe)


def _tune(pipe):
    """Làm pipeline nhạy hơn với đoạn ngắn nhưng vẫn tự đếm số người.
    Chỉnh bằng biến môi trường DIAR_THRESHOLD (mặc định pyannote ~0.70, thấp hơn = tách nhiều người hơn)
    và DIAR_MIN_CLUSTER (mặc định 12, nhỏ hơn = giữ người nói ít lời)."""
    try:
        params = pipe.parameters(instantiated=True)
        clustering = dict(params.get("clustering", {}))
        clustering["threshold"] = float(os.environ.get("DIAR_THRESHOLD", "0.55"))
        clustering["min_cluster_size"] = int(os.environ.get("DIAR_MIN_CLUSTER", "4"))
        params["clustering"] = clustering
        pipe.instantiate(params)
    except Exception as exc:
        print(f"[Diarization] Không chỉnh được tham số: {ascii(str(exc))}")
    return pipe


def diarize(wav_path, num_speakers=None):
    """Trả về [(start, end, speaker_label)]. num_speakers=None: tự phát hiện."""
    out = _load()(wav_path, num_speakers=num_speakers, min_speakers=1, max_speakers=8)
    ann = getattr(out, "speaker_diarization", out)  # tương thích pyannote 3.x và 4.x
    turns = [(t.start, t.end, spk) for t, _, spk in ann.itertracks(yield_label=True)]
    turns.sort(key=lambda x: x[0])
    return turns


def _split_segment(seg, turns):
    """Nếu một đoạn ASR trải qua nhiều người nói, chia chữ theo tỉ lệ thời gian."""
    pieces = []
    for s, e, spk in turns:
        a, b = max(seg["start"], s), min(seg["end"], e)
        if b - a > 0.3:
            pieces.append((a, b, spk))
    if len({p[2] for p in pieces}) < 2:
        return None
    words = seg["text"].split()
    total = sum(b - a for a, b, _ in pieces)
    if len(words) < len(pieces) or total <= 0:
        return None
    out, pos = [], 0
    for i, (a, b, spk) in enumerate(pieces):
        n = len(words) - pos if i == len(pieces) - 1 else max(1, round(len(words) * (b - a) / total))
        chunk = words[pos:pos + n]
        pos += n
        if chunk:
            out.append({"start": a, "end": b, "text": " ".join(chunk), "_spk": spk})
    return out


def assign_speakers(segments, turns):
    """Gán mỗi đoạn ASR cho người nói có thời gian chồng lấn lớn nhất.
    Đoạn dài chứa nhiều người nói sẽ được tách. Nhãn: Người 1, Người 2... theo thứ tự xuất hiện."""
    expanded = []
    for seg in segments:
        parts = _split_segment(seg, turns)
        expanded.extend(parts if parts else [seg])

    names, result = {}, []
    for seg in expanded:
        best = seg.pop("_spk", None)
        if best is None:
            best_ov = 0.0
            for s, e, spk in turns:
                ov = min(seg["end"], e) - max(seg["start"], s)
                if ov > best_ov:
                    best, best_ov = spk, ov
        if best is None:
            seg["speaker"] = "Chưa rõ"
        else:
            if best not in names:
                names[best] = f"Người {len(names) + 1}"
            seg["speaker"] = names[best]
        result.append(seg)
    segments[:] = result
    return segments


def format_transcript(segments):
    """Gộp các đoạn liên tiếp của cùng một người thành một dòng."""
    lines, cur, buf = [], None, []
    for seg in segments:
        if seg["speaker"] != cur and buf:
            lines.append(f"[{cur}] {' '.join(buf)}")
            buf = []
        cur = seg["speaker"]
        buf.append(seg["text"].strip())
    if buf:
        lines.append(f"[{cur}] {' '.join(buf)}")
    return "\n".join(lines)