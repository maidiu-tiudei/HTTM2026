"""Kiểm tra chọn bộ thực thi, đúng trọng số và duyệt đủ kết quả phiên âm."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import config
from asr import fast_runtime, transcriber


class FasterRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.ct2 = SimpleNamespace(get_cuda_device_count=lambda: 1,
                                   get_supported_compute_types=lambda device: {"int8_float16", "int8"})
        self.constructor = MagicMock(return_value=object())
        self.patches = [patch.object(config, "ASR_CT2_MODEL_DIR", self.directory),
                        patch.object(config, "ASR_DEVICE", "auto"),
                        patch.object(config, "ASR_COMPUTE_TYPE", "auto"),
                        patch.object(fast_runtime, "configure_nvidia_libraries"),
                        patch.dict("sys.modules", {"ctranslate2": self.ct2,
                                                   "faster_whisper": SimpleNamespace(WhisperModel=self.constructor)})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def make_model(self, source="vinai/PhoWhisper-large"):
        path = self.directory / "PhoWhisper-large-int8"
        path.mkdir()
        (path / "model.bin").write_bytes(b"test-model")
        (path / "source.json").write_text(json.dumps({"source_model": source, "source_revision": "test-revision"}))
        return path

    def test_gpu_uses_same_local_phowhisper_and_int8_float16(self):
        path = self.make_model()
        model, info = fast_runtime.load_faster_model("vinai/PhoWhisper-large")
        self.constructor.assert_called_once_with(str(path), device="cuda", compute_type="int8_float16",
                                                 num_workers=1, local_files_only=True)
        self.assertEqual(info["source_revision"], "test-revision")
        self.assertEqual(info["model"], "vinai/PhoWhisper-large")

    def test_no_cuda_uses_cpu_int8(self):
        self.make_model()
        self.ct2.get_cuda_device_count = lambda: 0
        _, info = fast_runtime.load_faster_model("vinai/PhoWhisper-large")
        self.assertEqual((info["device"], info["compute_type"]), ("cpu", "int8"))

    def test_wrong_source_and_missing_model_are_rejected_without_download(self):
        with self.assertRaisesRegex(RuntimeError, "prepare_asr_ct2"):
            fast_runtime.load_faster_model("vinai/PhoWhisper-large")
        self.make_model("openai/whisper-large-v2")
        with self.assertRaisesRegex(RuntimeError, "không khớp"):
            fast_runtime.load_faster_model("vinai/PhoWhisper-large")
        self.constructor.assert_not_called()

    def test_unsupported_compute_type_is_explicit(self):
        self.make_model()
        self.ct2.get_supported_compute_types = lambda device: {"float32"}
        with self.assertRaises(RuntimeError):
            fast_runtime.load_faster_model("vinai/PhoWhisper-large")
        self.constructor.assert_not_called()

    def test_lazy_segments_are_consumed_and_vietnamese_is_fixed(self):
        consumed = []

        def segments():
            for text in ("  Xin chào ", "", "cuộc họp."):
                consumed.append(text)
                yield SimpleNamespace(text=text)

        model = MagicMock()
        model.transcribe.return_value = (segments(), None)
        text = fast_runtime.transcribe_faster(model, np.zeros(16000, dtype=np.float32))
        self.assertEqual(text, "Xin chào cuộc họp.")
        self.assertEqual(len(consumed), 3)
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "vi")
        self.assertFalse(model.transcribe.call_args.kwargs["vad_filter"])

    def test_lazy_inference_error_is_not_swallowed(self):
        def segments():
            yield SimpleNamespace(text="Đầu câu")
            raise RuntimeError("CUDA out of memory")
        model = MagicMock()
        model.transcribe.return_value = (segments(), None)
        with self.assertRaisesRegex(RuntimeError, "out of memory"):
            fast_runtime.transcribe_faster(model, np.zeros(16000, dtype=np.float32))


class DispatcherTests(unittest.TestCase):
    def tearDown(self):
        transcriber._load_pipeline.cache_clear()
        transcriber._runtime_info.clear()

    def test_faster_model_is_loaded_only_once_and_reports_device(self):
        model = object()
        runtime = {"backend": "faster-whisper", "model": "vinai/PhoWhisper-large", "device": "cuda"}
        transcriber._load_pipeline.cache_clear()
        with patch.object(config, "ASR_BACKEND", "faster-whisper"), \
                patch.object(fast_runtime, "load_faster_model", return_value=(model, runtime)) as load:
            self.assertIs(transcriber._load_pipeline(runtime["model"]), model)
            self.assertIs(transcriber._load_pipeline(runtime["model"]), model)
        load.assert_called_once()
        self.assertEqual(transcriber.get_asr_runtime(), runtime)

    def test_transformers_backend_keeps_existing_model_and_output_contract(self):
        model = SimpleNamespace(device="cpu", model=SimpleNamespace(dtype="torch.float32"))
        factory = MagicMock(return_value=model)
        transcriber._load_pipeline.cache_clear()
        with patch.object(config, "ASR_BACKEND", "transformers"), \
                patch.dict("sys.modules", {"transformers": SimpleNamespace(pipeline=factory)}):
            self.assertIs(transcriber._load_pipeline("vinai/PhoWhisper-large"), model)
        factory.assert_called_once_with("automatic-speech-recognition", model="vinai/PhoWhisper-large")
        self.assertEqual(transcriber.get_asr_runtime()["backend"], "transformers")


if __name__ == "__main__":
    unittest.main()
