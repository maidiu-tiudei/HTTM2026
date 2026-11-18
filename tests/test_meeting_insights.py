import json
import unittest
from unittest.mock import patch

from asr.diarization import speaker_timeline
from nlp.meeting_chat import NO_EVIDENCE, answer_meeting


class SpeakerTimelineTests(unittest.TestCase):
    def test_splits_whisper_segment_at_speaker_change(self):
        segments = [{"start": 12.0, "end": 17.0, "text": "Chào bạn đúng vậy", "words": [
            {"start": 12.0, "end": 13.2, "text": "Chào bạn"},
            {"start": 14.0, "end": 15.1, "text": "đúng vậy"},
            {"start": 16.0, "end": 17.0, "text": "chờ nhé"},
        ]}]
        turns = [(12.0, 13.8, 7), (14.0, 15.3, 3), (16.0, 17.0, 7)]
        rows = speaker_timeline(segments, turns)
        self.assertEqual([row["speaker_id"] for row in rows], ["S1", "S2", "S1"])
        self.assertEqual([(row["start"], row["text"]) for row in rows],
                         [(12.0, "Chào bạn"), (14.0, "đúng vậy"), (16.0, "chờ nhé")])

    def test_overlap_and_unmatched_audio_do_not_invent_speaker(self):
        segments = [{"start": 5.0, "end": 6.0, "text": "Đồng ý"},
                    {"start": 8.0, "end": 9.0, "text": "Bắt đầu"}]
        rows = speaker_timeline(segments, [(5, 6, 1), (5, 6, 2)])
        self.assertEqual([row["speaker_id"] for row in rows], [None, None])
        self.assertEqual([row["text"] for row in rows], ["Đồng ý", "Bắt đầu"])

    def test_attaches_short_opener_to_next_speaker_across_asr_segments(self):
        segments = [
            {"start": 0.576, "end": 14.256, "text": "Xong chưa Tuấn .dạ", "words": [
                {"start": 0.576, "end": 13.016, "text": "Xong chưa Tuấn"},
                {"start": 13.016, "end": 14.256, "text": ".dạ"},
            ]},
            {"start": 14.256, "end": 23.256, "text": "em đã gọi bên bảo hành"},
        ]
        turns = [(0.571, 13.092, 0), (13.953, 23.150, 1)]
        self.assertEqual(speaker_timeline(segments, turns), [
            {"id": 1, "speaker_id": "S1", "start": 0.576, "end": 13.016, "text": "Xong chưa Tuấn"},
            {"id": 2, "speaker_id": "S2", "start": 13.016, "end": 23.256,
             "text": "dạ em đã gọi bên bảo hành"},
        ])

    def test_leaves_short_acknowledgement_unknown_without_clear_next_voice(self):
        segments = [{"start": 1, "end": 2, "text": "Bạn xử lý nhé"},
                    {"start": 2, "end": 3, "text": "Vâng"},
                    {"start": 3, "end": 4, "text": "Em sẽ gửi sớm"}]
        for turns in ([(1, 2, 0), (3, 4, 1)], [(1, 2, 0), (2.7, 4, 1), (2.7, 3, 2)]):
            with self.subTest(turns=turns):
                rows = speaker_timeline(segments, turns)
                self.assertEqual([row["speaker_id"] for row in rows], ["S1", None, "S2"])


class MeetingChatTests(unittest.TestCase):
    def ask(self, meeting, response):
        def respond(prompt, key, validate, **kwargs):
            self.prompt = json.loads(prompt)
            return validate(response)
        with patch("nlp.meeting_chat.config.get_api_keys", return_value=("fake", None)), \
                patch("nlp.meeting_chat.generate_gemini_json", side_effect=respond):
            return answer_meeting(meeting, "Ai phụ trách kiểm thử?", [])

    def test_only_existing_quote_gets_timestamp_and_speaker(self):
        row = {"id": 1, "text": "Mai phụ trách kiểm thử.", "start": 12.0, "end": 14.5, "speaker_id": "S1"}
        response = {"answer": "Mai phụ trách kiểm thử.", "citations": [
            {"source_id": 9, "quote": "Nguồn không có"},
            {"source_id": 1, "quote": "Mai phụ trách kiểm thử."},
        ]}
        result = self.ask({"speaker_segments": [row]}, response)
        self.assertEqual(result["citations"], [
            {"id": 1, "quote": row["text"], "start": 12.0, "end": 14.5, "speaker_id": "S1"},
        ])

    def test_edited_transcript_has_no_stale_timestamps_or_raw_text(self):
        meeting = {"transcript": "Nam phụ trách.", "transcript_edited": "Mai phụ trách.",
                   "transcript_revision": 2,
                   "speaker_segments": [{"id": 1, "text": "Nam phụ trách.", "start": 1, "end": 2, "speaker_id": "S1"}]}
        result = self.ask(meeting, {"answer": "Mai", "citations": [{"source_id": 1, "quote": "Mai phụ trách."}]})
        self.assertEqual(self.prompt["sources"], [{"id": 1, "text": "Mai phụ trách."}])
        self.assertNotIn("start", result["citations"][0])
        self.assertEqual(result["transcript_revision"], 2)

    def test_hallucinated_quote_cannot_support_an_answer(self):
        result = self.ask({"transcript": "Nhóm thống nhất họp vào thứ sáu."},
                          {"answer": "Mai phụ trách", "citations": [{"source_id": 1, "quote": "Mai phụ trách"}]})
        self.assertEqual(result["answer"], NO_EVIDENCE)
        self.assertEqual(result["citations"], [])
