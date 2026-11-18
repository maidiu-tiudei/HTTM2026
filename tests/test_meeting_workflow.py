"""Kiểm thử bằng dữ liệu tạm; không gọi AI và không chạm dữ liệu cuộc họp thật."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from backend import app as api, pipeline, storage
from nlp.errors import SummaryError, classify_summary_error
from nlp.schema import SummaryValidationError, validate_summary
from nlp.summarizer import summarize_transcript, summarize_with_gemini


def valid_summary():
    return {
        "metadata": {"tieu_de": "Họp thử", "thoi_luong": "Chưa rõ",
                     "ngay_thuc_hien": "04/11/2026", "thanh_phan_tham_du": []},
        "tong_quan": "Nhóm thống nhất kiểm thử bản cập nhật.",
        "noi_dung_thao_luan": [{"chu_de": "Kiểm thử", "chi_tiet": ["Đối chiếu audio."]}],
        "quyet_dinh": ["Kiểm thử trước khi demo"],
        "action_items": [{"cong_viec": "Kiểm thử", "nguoi_phu_trach": "Chưa rõ",
                          "deadline": "Chưa rõ", "uu_tien": "Trung bình"}],
    }


class SchemaTests(unittest.TestCase):
    def test_valid_and_empty_optional_lists(self):
        data = valid_summary()
        data.update(action_items=[], quyet_dinh=[], noi_dung_thao_luan=[])
        self.assertEqual(validate_summary(data), data)

    def test_missing_or_wrong_nested_types_are_rejected(self):
        for field, value in [("metadata", []), ("tong_quan", None),
                             ("action_items", "công việc"), ("quyet_dinh", [3]),
                             ("noi_dung_thao_luan", [{"chu_de": "Test", "chi_tiet": "sai"}])]:
            with self.subTest(field=field):
                data = valid_summary()
                data[field] = value
                with self.assertRaises(SummaryValidationError):
                    validate_summary(data)

    def test_missing_task_field_and_invalid_priority(self):
        for key in ("deadline", "nguoi_phu_trach", "uu_tien"):
            data = valid_summary()
            del data["action_items"][0][key]
            with self.assertRaises(SummaryValidationError):
                validate_summary(data)
        data = valid_summary()
        data["action_items"][0]["uu_tien"] = "Khẩn cấp"
        with self.assertRaises(SummaryValidationError):
            validate_summary(data)

    def test_error_categories_do_not_expose_sdk_details(self):
        for status, expected in [(401, "invalid_key"), (403, "invalid_key"), (429, "rate_limit"),
                                 (504, "timeout"), (503, "unavailable"), (404, "model_not_found"),
                                 (400, "configuration")]:
            error = RuntimeError("secret-api-key")
            error.code = status
            result = classify_summary_error(error)
            self.assertEqual(result.code, expected)
            self.assertNotIn("secret-api-key", str(result))
        self.assertEqual(classify_summary_error(TimeoutError()).code, "timeout")

    def test_missing_key_is_explicit(self):
        with patch("config.get_api_keys", return_value=(None, None)):
            with self.assertRaises(SummaryError) as caught:
                summarize_transcript("Nội dung")
        self.assertEqual(caught.exception.code, "missing_key")

    def test_gemini_falls_back_after_invalid_json(self):
        client = MagicMock()
        client.models.generate_content.side_effect = [
            SimpleNamespace(text="không phải json"),
            SimpleNamespace(text=json.dumps(valid_summary())),
        ]
        with patch("google.genai.Client", return_value=client), patch("config.GEMINI_MODELS", ["a", "b"]):
            self.assertEqual(summarize_with_gemini("Nội dung", "test-key"), valid_summary())
        self.assertEqual(client.models.generate_content.call_count, 2)
        client.close.assert_called_once()

    def test_gemini_stops_on_auth_error(self):
        client = MagicMock()
        error = RuntimeError("API key not valid: secret")
        client.models.generate_content.side_effect = error
        with patch("google.genai.Client", return_value=client), patch("config.GEMINI_MODELS", ["a", "b"]):
            with self.assertRaises(SummaryError) as caught:
                summarize_with_gemini("Nội dung", "test-key")
        self.assertEqual(caught.exception.code, "invalid_key")
        self.assertEqual(client.models.generate_content.call_count, 1)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch.object(storage, "DB", root / "meetings.json"),
                        patch.object(pipeline, "OUT", root), patch.object(pipeline, "UPLOADS", root)]
        for item in self.patches:
            item.start()
        self.client = TestClient(api.app)
        storage.add_meeting({"id": "sample", "title": "Họp thử", "created": "2026-11-04T10:00:00",
                             "status": "done", "summary_status": "done", "sec": 36,
                             "transcript": "Transcript ASR gốc", "summary": valid_summary(),
                             "minutes": "Biên bản cũ", "transcript_revision": 0,
                             "timings": {"asr_seconds": 2, "initial_pipeline_seconds": 4}})

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def get(self):
        return storage.get_meeting("sample")

    def edit(self, text="Transcript đã chỉnh", revision=0):
        return self.client.patch("/api/meetings/sample/transcript",
                                 json={"text": text, "expected_revision": revision})

    def test_edit_preserves_raw_and_marks_old_summary(self):
        response = self.edit()
        self.assertEqual(response.status_code, 200)
        meeting = response.json()
        self.assertEqual(meeting["transcript"], "Transcript ASR gốc")
        self.assertEqual(meeting["transcript_edited"], "Transcript đã chỉnh")
        self.assertEqual(meeting["transcript_revision"], 1)
        self.assertTrue(meeting["summary_outdated"])
        self.assertEqual(meeting["minutes"], "Biên bản cũ")

    def test_blank_wrong_type_and_too_long_edit_rejected(self):
        for value in ("  ", "", 42, "x" * 200001):
            self.assertEqual(self.edit(value).status_code, 422)
        self.assertNotIn("transcript_edited", self.get())

    def test_revision_conflict_does_not_overwrite(self):
        self.edit("Bản thứ nhất")
        self.assertEqual(self.edit("Bản ghi đè", revision=0).status_code, 409)
        self.assertEqual(self.get()["transcript_edited"], "Bản thứ nhất")

    def test_same_text_does_not_increment_revision(self):
        self.assertEqual(self.edit("Transcript ASR gốc").json()["transcript_revision"], 0)

    def test_edit_and_retry_blocked_while_busy(self):
        for busy in ({"status": "processing"}, {"summary_status": "processing"},
                     {"pipeline_status": "processing"}):
            storage.update_meeting("sample", status="done", summary_status="done", pipeline_status="done", **{
                key: val for key, val in busy.items() if key not in ("status", "summary_status", "pipeline_status")
            })
            storage.update_meeting("sample", **busy)
            self.assertEqual(self.edit().status_code, 409)
            self.assertEqual(self.client.post("/api/meetings/sample/retry-summary").status_code, 409)

    def test_missing_meeting_and_missing_transcript(self):
        self.assertEqual(self.client.patch("/api/meetings/missing/transcript", json={"text": "x", "expected_revision": 0}).status_code, 404)
        self.assertEqual(self.client.post("/api/meetings/missing/retry-summary").status_code, 404)
        storage.update_meeting("sample", transcript="")
        self.assertEqual(self.edit().status_code, 409)
        self.assertEqual(self.client.post("/api/meetings/sample/retry-summary").status_code, 409)

    def test_retry_uses_saved_edit_without_asr(self):
        self.edit()
        with patch.object(pipeline, "summarize_transcript", return_value=valid_summary()) as summarize, \
                patch.object(pipeline, "transcribe_audio") as asr:
            response = self.client.post("/api/meetings/sample/retry-summary")
        self.assertEqual(response.status_code, 200)
        summarize.assert_called_once_with("Transcript đã chỉnh")
        asr.assert_not_called()
        meeting = self.get()
        self.assertFalse(meeting["summary_outdated"])
        self.assertEqual(meeting["summary_transcript_revision"], 1)
        self.assertEqual(meeting["summary_status"], "done")
        self.assertGreaterEqual(meeting["timings"]["summary_seconds"], 0)
        self.assertEqual(meeting["timings"]["asr_seconds"], 2)
        self.assertEqual(meeting["timings"]["initial_pipeline_seconds"], 4)

    def test_failed_retry_preserves_old_summary_and_reports_specific_error(self):
        self.edit()
        before = self.get()
        with patch.object(pipeline, "summarize_transcript", side_effect=SummaryError("timeout")):
            self.client.post("/api/meetings/sample/retry-summary")
        meeting = self.get()
        self.assertEqual(meeting["summary"], before["summary"])
        self.assertEqual(meeting["minutes"], before["minutes"])
        self.assertEqual(meeting["summary_error_code"], "timeout")
        self.assertEqual(meeting["summary_status"], "error")
        self.assertTrue(meeting["summary_outdated"])

    def test_invalid_ai_output_cannot_replace_old_summary(self):
        with patch.object(pipeline, "summarize_transcript", return_value={"tong_quan": "Thiếu trường"}):
            pipeline.retry_meeting_summary("sample")
        self.assertEqual(self.get()["summary"], valid_summary())
        self.assertEqual(self.get()["summary_error_code"], "invalid_response")

    def test_file_write_failure_keeps_old_summary(self):
        with patch.object(pipeline, "OUT", Path(self.tmp.name) / "missing"), \
                patch.object(pipeline, "summarize_transcript", return_value=valid_summary()):
            pipeline.retry_meeting_summary("sample")
        self.assertEqual(self.get()["minutes"], "Biên bản cũ")
        self.assertEqual(self.get()["summary_error_code"], "storage_error")

    def test_initial_pipeline_records_stages_and_durations(self):
        seen = []
        original = storage.update_meeting

        def track(mid, **fields):
            if "stage" in fields:
                seen.append(fields["stage"])
            original(mid, **fields)

        original_time = pipeline.record_time

        def track_time(mid, name, started, **fields):
            if "stage" in fields:
                seen.append(fields["stage"])
            return original_time(mid, name, started, **fields)

        with patch.object(pipeline, "to_wav"), patch.object(pipeline.sf, "info", return_value=SimpleNamespace(duration=36)), \
                patch.object(pipeline, "transcribe_audio", return_value=("Transcript mới", [])), \
                patch.object(pipeline, "summarize_transcript", return_value=valid_summary()), \
                patch.object(pipeline, "update_meeting", side_effect=track), \
                patch.object(pipeline, "record_time", side_effect=track_time):
            pipeline.process_meeting("sample", Path("fake.mp3"))
        meeting = self.get()
        self.assertEqual(meeting["stage"], "done")
        self.assertEqual(meeting["pipeline_status"], "done")
        for stage in ("converting", "waiting_asr", "transcribing", "summarizing", "done"):
            self.assertIn(stage, seen)
        for key in ("conversion_seconds", "queue_seconds", "asr_seconds", "summary_seconds", "initial_pipeline_seconds"):
            self.assertGreaterEqual(meeting["timings"][key], 0)

    def test_audio_failure_records_failed_stage_and_time(self):
        with patch.object(pipeline, "to_wav", side_effect=RuntimeError("Invalid audio")):
            pipeline.process_meeting("sample", Path("fake.mp3"))
        meeting = self.get()
        self.assertEqual(meeting["stage"], "error")
        self.assertEqual(meeting["failed_stage"], "converting")
        self.assertIn("initial_pipeline_seconds", meeting["timings"])
        self.assertEqual(meeting["pipeline_status"], "done")

    def test_simultaneous_retries_start_only_one_background_job(self):
        barrier = threading.Barrier(2)

        def begin():
            jobs = BackgroundTasks()
            barrier.wait()
            try:
                api.retry_summary("sample", jobs)
                return len(jobs.tasks)
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: begin(), range(2)))
        self.assertEqual(sorted(results), [1, 409])

    def test_failed_database_replace_does_not_damage_old_data(self):
        before = storage.DB.read_bytes()
        with patch.object(storage.os, "replace", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                storage.update_meeting("sample", minutes="Không được ghi")
        self.assertEqual(storage.DB.read_bytes(), before)
        self.assertEqual(list(storage.DB.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
