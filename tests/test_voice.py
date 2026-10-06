"""Microphone, cache and archive safety tests without live audio or network."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from dictionary_app import voice


def model_zip(name: str, extra: dict[str, bytes] | None = None) -> bytes:
    members = {
        f"{name}/am/final.mdl": b"am",
        f"{name}/conf/model.conf": b"conf",
        f"{name}/graph/HCLG.fst": b"graph",
    }
    members.update(extra or {})
    result = BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in members.items():
            archive.writestr(path, content)
    return result.getvalue()


class FakeResponse(BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))}


class VoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name)

    def test_first_use_downloads_to_private_cache_then_reuses_model(self) -> None:
        name = voice.MODEL_NAMES["zh"]
        archive = model_zip(name)
        updates: list[str] = []
        with mock.patch("dictionary_app.voice.get_app_data_dir", return_value=self.data_dir), \
             mock.patch("dictionary_app.voice.urlopen", return_value=FakeResponse(archive)) as download:
            model_path = voice.get_model_path("zh", updates.append)
            self.assertEqual(model_path, self.data_dir / "models" / name)
            self.assertTrue((model_path / "am" / "final.mdl").is_file())
            self.assertIn("speech model is ready", updates[-1])
            self.assertEqual(voice.get_model_path("zh"), model_path)
            download.assert_called_once()

    def test_zip_traversal_is_rejected_and_no_model_is_installed(self) -> None:
        name = voice.MODEL_NAMES["en"]
        archive = model_zip(name, {f"{name}/../../escape.txt": b"bad"})
        with mock.patch("dictionary_app.voice.get_app_data_dir", return_value=self.data_dir), \
             mock.patch("dictionary_app.voice.urlopen", return_value=FakeResponse(archive)):
            with self.assertRaisesRegex(voice.VoiceError, "unsafe file path"):
                voice.get_model_path("en")
        self.assertFalse((self.data_dir / "models" / name).exists())
        self.assertFalse((self.data_dir / "escape.txt").exists())

    def test_invalid_language_and_missing_optional_dependencies(self) -> None:
        with self.assertRaises(ValueError):
            voice.VoiceRecorder("fr")
        with mock.patch("dictionary_app.voice.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(voice.VoiceError, "optional"):
                voice.VoiceRecorder("en").start()

    def test_recording_returns_editable_chinese_transcript(self) -> None:
        blocks = []
        levels = []

        class FakeStream:
            def __init__(self, **kwargs) -> None:
                self.callback = kwargs["callback"]
                self.closed = False

            def start(self) -> None:
                self.callback(b"\x10\x00" * 1_000, 1_000, None, None)

            def stop(self) -> None:
                pass

            def close(self) -> None:
                self.closed = True

        class FakeSoundDevice:
            CallbackStop = RuntimeError
            RawInputStream = FakeStream

        class FakeRecognizer:
            def __init__(self, model, sample_rate) -> None:
                self.sample_rate = sample_rate

            def AcceptWaveform(self, audio) -> bool:
                blocks.append(audio)
                return False

            def FinalResult(self) -> str:
                return json.dumps({"text": "我 今 天 学 了 厄 瑞 波 斯"})

        class FakeVosk:
            Model = str
            KaldiRecognizer = FakeRecognizer

        def dependency(name: str):
            return FakeSoundDevice if name == "sounddevice" else FakeVosk

        recorder = voice.VoiceRecorder("zh", on_level=levels.append)
        with mock.patch("dictionary_app.voice._load_voice_dependency", side_effect=dependency), \
             mock.patch("dictionary_app.voice.get_model_path", return_value=self.data_dir):
            recorder.start()
            transcript = recorder.stop_and_transcribe()
        self.assertEqual(transcript, "我今天学了厄瑞波斯")
        self.assertEqual(b"".join(blocks), b"\x10\x00" * 1_000)
        self.assertEqual(len(levels), 1)
        self.assertGreater(levels[0], 0)
        self.assertIsNone(recorder._stream)


if __name__ == "__main__":
    unittest.main()
