"""Tách lượt nói và gắn lời phiên âm vào các lượt theo mốc audio gốc."""
import re
import threading
import unicodedata
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

import soundfile as sf

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "diarization"
SEGMENTATION = MODEL_DIR / "segmentation.onnx"
EMBEDDING = MODEL_DIR / "embedding.onnx"
_lock = threading.Lock()
_TURN_OPENERS = {"dạ", "vâng", "dạ vâng", "vâng ạ", "dạ ạ"}


@lru_cache(maxsize=1)
def _model():
    if not (SEGMENTATION.is_file() and EMBEDDING.is_file()):
        raise RuntimeError("Chưa có model tách người nói. Chạy py -3.10 -m scripts.prepare_diarization.")
    try:
        import sherpa_onnx as sherpa
    except ImportError as exc:
        raise RuntimeError("Chưa cài sherpa-onnx. Chạy py -3.10 -m pip install -r requirements.txt.") from exc
    settings = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(SEGMENTATION)),
            num_threads=2, provider="cpu",
        ),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(model=str(EMBEDDING), num_threads=2, provider="cpu"),
        clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=0.5),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not settings.validate():
        raise RuntimeError("Cấu hình model tách người nói không hợp lệ.")
    return sherpa.OfflineSpeakerDiarization(settings)


def identify_turns(wav):
    audio, rate = sf.read(wav, dtype="float32", always_2d=True)
    with _lock:
        model = _model()
        if rate != model.sample_rate:
            raise RuntimeError("Cần WAV mono 16 kHz để tách người nói.")
        turns = model.process(audio.mean(axis=1)).sort_by_start_time()
    return [(turn.start, turn.end, turn.speaker) for turn in turns]


def _overlap_scores(start, end, turns, starts, longest):
    scores = {}
    for a, b, speaker in turns[bisect_left(starts, start - longest):bisect_left(starts, end)]:
        overlap = min(end, b) - max(start, a)
        if overlap > 0:
            scores[speaker] = max(scores.get(speaker, 0), overlap)
    return scores


def _attach_turn_openers(timeline, labels, turns, starts, longest):
    speakers = {label: speaker for speaker, label in labels.items()}
    result = []
    for index, row in enumerate(timeline):
        if row["speaker_id"] is not None or not (0 < index < len(timeline) - 1):
            result.append(row)
            continue

        previous, following = timeline[index - 1], timeline[index + 1]
        before, after = previous["speaker_id"], following["speaker_id"]
        start, end = row["start"], row["end"]
        words = re.findall(r"\w+", unicodedata.normalize("NFC", row["text"]).lower())
        if (not before or not after or before == after or end - start > 1.5
                or abs(start - previous["end"]) > 0.35 or abs(following["start"] - end) > 0.35
                or " ".join(words) not in _TURN_OPENERS):
            result.append(row)
            continue

        scores = _overlap_scores(start, end, turns, starts, longest)
        upcoming = scores.pop(speakers[after], 0)
        competing = max(scores.values(), default=0)
        # Chấp nhận phần dư rất ngắn của giọng trước ở ranh giới, nếu giọng sau rõ hơn.
        if upcoming < 0.1 or competing > 0.1 or upcoming < 2 * competing:
            result.append(row)
            continue

        following["start"] = min(start, following["start"])
        opener = row["text"].lstrip(".!?… ").rstrip()
        following["text"] = f"{opener} {following['text']}"
    return result


def speaker_timeline(segments, turns):
    """Giữ thứ tự lời nói. Gán mỗi từ theo phần giao thời gian với từng giọng."""
    timeline = []
    labels = {}
    ordered = sorted(turns)
    starts = [turn[0] for turn in ordered]
    longest = max((end - start for start, end, _ in ordered), default=0)
    for segment in segments:
        units = segment.get("words") or [segment]
        groups = []
        for unit in units:
            start, end, value = unit["start"], unit["end"], unit["text"].strip()
            if not value:
                continue
            scores = _overlap_scores(start, end, ordered, starts, longest)
            ranked = sorted(scores, key=scores.get, reverse=True)
            label = None
            if (ranked and scores[ranked[0]] >= (end - start) * 0.5
                    and (len(ranked) == 1 or scores[ranked[0]] - scores[ranked[1]] > (end - start) * 0.1)):
                speaker = ranked[0]
                label = labels.setdefault(speaker, f"S{len(labels) + 1}")
            if groups and groups[-1]["speaker_id"] == label and start - groups[-1]["end"] < 1:
                groups[-1]["end"] = max(groups[-1]["end"], end)
                groups[-1]["text"] += " " + value
            else:
                groups.append({"speaker_id": label, "start": start, "end": end, "text": value})
        timeline.extend(groups)
    timeline = _attach_turn_openers(timeline, labels, ordered, starts, longest)
    return [dict(row, id=index) for index, row in enumerate(timeline, 1)]
