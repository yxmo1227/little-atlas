"""Opt-in offline Chinese and English microphone transcription.

Neither sounddevice nor Vosk is imported until the microphone is used. Model
archives come from the official Vosk model catalogue and are cached in the
current user's application data directory, never in the source checkout.
"""

from __future__ import annotations

from array import array
import importlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import threading
from typing import Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from .storage import get_app_data_dir


Language = Literal["zh", "en"]
ProgressCallback = Callable[[str], None]
LevelCallback = Callable[[float], None]

MODEL_NAMES: dict[Language, str] = {
    "zh": "vosk-model-small-cn-0.22",
    "en": "vosk-model-small-en-us-0.15",
}
MODEL_LABELS: dict[Language, str] = {"zh": "Chinese", "en": "English"}
MODEL_BASE_URL = "https://alphacephei.com/vosk/models/"
SAMPLE_RATE = 16_000
MAX_ARCHIVE_BYTES = 160 * 1024 * 1024
MAX_UNPACKED_BYTES = 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 5_000
MAX_RECORD_SECONDS = 20 * 60
_model_lock = threading.Lock()


class VoiceError(RuntimeError):
    """A microphone, model download, or recognition failure the UI may show."""


def _emit(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        try:
            callback(message)
        except Exception:
            # Presentation callbacks must not corrupt a model installation.
            pass


def _valid_model(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "am" / "final.mdl").is_file()
        and (path / "conf" / "model.conf").is_file()
        and (path / "graph" / "HCLG.fst").is_file()
    )


def _safe_member_path(root: Path, member: zipfile.ZipInfo, model_name: str) -> Path:
    """Resolve a zip member without allowing traversal, links, or extra roots."""
    name = member.filename.replace("\\", "/")
    parts = name.rstrip("/").split("/")
    if (
        not parts or parts[0] != model_name
        or any(part in ("", ".", "..") or ":" in part for part in parts)
        or name.startswith("/")
    ):
        raise VoiceError("The downloaded speech model contains an unsafe file path.")
    # Unix external attributes encode the member's file type.  A symlink may
    # otherwise let later files escape the temporary extraction directory.
    mode = (member.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise VoiceError("The downloaded speech model contains an unsafe link.")
    destination = root.joinpath(*parts)
    try:
        destination.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise VoiceError("The downloaded speech model contains an unsafe file path.") from exc
    return destination


def _download_model_archive(url: str, destination: Path, language: Language,
                            on_progress: ProgressCallback | None) -> None:
    request = Request(url, headers={"User-Agent": "PersonalDictionary/1.0"})
    try:
        with urlopen(request, timeout=30) as response, destination.open("wb") as output:
            declared = response.headers.get("Content-Length")
            total = int(declared) if declared and declared.isdecimal() else None
            if total is not None and total > MAX_ARCHIVE_BYTES:
                raise VoiceError("The speech model download is unexpectedly large.")
            downloaded = 0
            last_display = -1
            while True:
                block = response.read(256 * 1024)
                if not block:
                    break
                downloaded += len(block)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise VoiceError("The speech model download is unexpectedly large.")
                output.write(block)
                if total:
                    display = min(100, downloaded * 100 // total)
                    if display // 5 != last_display // 5:
                        _emit(on_progress, f"Downloading {MODEL_LABELS[language]} speech model: {display}%")
                        last_display = display
                else:
                    display = downloaded // (1024 * 1024)
                    if display != last_display:
                        _emit(on_progress,
                              f"Downloading {MODEL_LABELS[language]} speech model: {display} MB")
                        last_display = display
            if downloaded == 0:
                raise VoiceError("The speech model download was empty.")
    except VoiceError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VoiceError(
            f"Could not download the {MODEL_LABELS[language]} speech model. "
            "Check your internet connection and try again."
        ) from exc


def _unpack_model_archive(archive: Path, extraction_root: Path, model_name: str,
                          on_progress: ProgressCallback | None) -> Path:
    _emit(on_progress, "Unpacking the speech model…")
    try:
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            if not members or len(members) > MAX_ZIP_MEMBERS:
                raise VoiceError("The speech model archive is invalid or unexpectedly large.")
            total_unpacked = sum(member.file_size for member in members)
            if total_unpacked > MAX_UNPACKED_BYTES:
                raise VoiceError("The speech model archive is unexpectedly large.")
            for member in members:
                destination = _safe_member_path(extraction_root, member, model_name)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
    except VoiceError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise VoiceError("The downloaded speech model could not be unpacked.") from exc
    model_path = extraction_root / model_name
    if not _valid_model(model_path):
        raise VoiceError("The downloaded speech model is incomplete.")
    return model_path


def get_model_path(language: Language,
                   on_progress: ProgressCallback | None = None) -> Path:
    """Return a validated cached model, downloading it on the first use.

    The first call needs internet access. A partially downloaded or invalid
    archive never becomes the active model. The callback may run on a worker
    thread, so a Qt UI should forward its text through a signal.
    """
    if language not in MODEL_NAMES:
        raise ValueError("language must be 'zh' or 'en'")
    model_name = MODEL_NAMES[language]
    models_dir = get_app_data_dir() / "models"
    model_path = models_dir / model_name
    if model_path.is_symlink():
        raise VoiceError("The cached speech model path is unsafe.")
    if _valid_model(model_path):
        return model_path
    with _model_lock:
        if model_path.is_symlink():
            raise VoiceError("The cached speech model path is unsafe.")
        if _valid_model(model_path):
            return model_path
        models_dir.mkdir(parents=True, exist_ok=True)
        _emit(on_progress, f"Preparing {MODEL_LABELS[language]} speech model…")
        with tempfile.TemporaryDirectory(prefix="model-", dir=models_dir) as temporary:
            temporary_path = Path(temporary)
            archive = temporary_path / "model.zip"
            extraction_root = temporary_path / "unpacked"
            extraction_root.mkdir()
            url = f"{MODEL_BASE_URL}{model_name}.zip"
            _download_model_archive(url, archive, language, on_progress)
            unpacked = _unpack_model_archive(
                archive, extraction_root, model_name, on_progress
            )
            if model_path.exists():
                if model_path.is_symlink():
                    raise VoiceError("The cached speech model path is unsafe.")
                try:
                    if model_path.is_dir():
                        shutil.rmtree(model_path)
                    else:
                        model_path.unlink()
                except OSError as exc:
                    raise VoiceError("The cached speech model could not be replaced.") from exc
            try:
                unpacked.rename(model_path)
            except OSError as exc:
                raise VoiceError("The speech model could not be installed.") from exc
        _emit(on_progress, f"{MODEL_LABELS[language]} speech model is ready.")
        return model_path


def _load_voice_dependency(name: str):
    try:
        return importlib.import_module(name)
    except (ImportError, OSError) as exc:
        raise VoiceError(
            "Microphone transcription needs the optional 'vosk' and "
            "'sounddevice' packages. Install the voice extras and try again."
        ) from exc


class VoiceRecorder:
    """Capture PCM audio promptly; transcribe only after recording stops.

    ``start`` opens a PortAudio callback stream and returns immediately.
    ``stop_and_transcribe`` may download a model and should be called from a
    worker thread. ``on_level`` is invoked from the audio callback thread.
    """

    def __init__(self, language: Language,
                 on_level: LevelCallback | None = None,
                 on_progress: ProgressCallback | None = None) -> None:
        if language not in MODEL_NAMES:
            raise ValueError("language must be 'zh' or 'en'")
        self.language = language
        self.on_level = on_level
        self.on_progress = on_progress
        self._lock = threading.Lock()
        self._audio = bytearray()
        self._stream = None
        self._capture_error: VoiceError | None = None

    def start(self) -> None:
        if self._stream is not None:
            raise VoiceError("The microphone is already recording.")
        sounddevice = _load_voice_dependency("sounddevice")
        _load_voice_dependency("vosk")
        with self._lock:
            self._audio.clear()
            self._capture_error = None

        def capture(indata, frames, time_info, status) -> None:
            block = bytes(indata)
            with self._lock:
                if len(self._audio) + len(block) > MAX_RECORD_SECONDS * SAMPLE_RATE * 2:
                    self._capture_error = VoiceError(
                        "Recording reached the 20-minute limit. Please make a shorter note."
                    )
                    raise sounddevice.CallbackStop()
                self._audio.extend(block)
            if self.on_level is not None:
                samples = array("h")
                samples.frombytes(block)
                if samples:
                    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
                    try:
                        self.on_level(min(1.0, rms / 10_000))
                    except Exception:
                        pass

        try:
            stream = sounddevice.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=4_000,
                callback=capture,
            )
            stream.start()
        except Exception as exc:
            if "stream" in locals():
                stream.close()
            raise VoiceError(
                "Could not open the microphone. Check device access and try again."
            ) from exc
        self._stream = stream
        _emit(self.on_progress, "Recording…")

    def _finish_stream(self) -> bytes:
        stream = self._stream
        if stream is None:
            raise VoiceError("The microphone is not recording.")
        self._stream = None
        stream_error: VoiceError | None = None
        try:
            stream.stop()
        except Exception as exc:
            stream_error = VoiceError("Could not stop the microphone recording.")
        try:
            stream.close()
        except Exception as exc:
            if stream_error is None:
                stream_error = VoiceError("Could not close the microphone recording.")
        with self._lock:
            audio = bytes(self._audio)
            self._audio.clear()
            error = self._capture_error
            self._capture_error = None
        if stream_error is not None:
            raise stream_error
        if error is not None:
            raise error
        return audio

    def cancel(self) -> None:
        """Discard the current recording without recognition."""
        if self._stream is not None:
            try:
                self._finish_stream()
            except VoiceError:
                pass
        with self._lock:
            self._audio.clear()

    def stop_and_transcribe(self) -> str:
        """Stop recording and return editable Chinese or English text."""
        audio = self._finish_stream()
        if not audio:
            raise VoiceError("No audio was recorded. Try speaking closer to the microphone.")
        model_path = get_model_path(self.language, self.on_progress)
        _emit(self.on_progress, "Transcribing your note…")
        vosk = _load_voice_dependency("vosk")
        try:
            model = vosk.Model(str(model_path))
            recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
            parts: list[str] = []
            for offset in range(0, len(audio), 8_000):
                if recognizer.AcceptWaveform(audio[offset:offset + 8_000]):
                    parts.append(json.loads(recognizer.Result()).get("text", ""))
            parts.append(json.loads(recognizer.FinalResult()).get("text", ""))
        except Exception as exc:
            raise VoiceError("The recording could not be transcribed. Please try again.") from exc
        transcript = " ".join(part.strip() for part in parts if part.strip()).strip()
        if self.language == "zh":
            transcript = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", transcript)
        if not transcript:
            raise VoiceError("No speech was recognized. Try again or type your note.")
        _emit(self.on_progress, "Transcription ready. You can edit the text before adding it.")
        return transcript
