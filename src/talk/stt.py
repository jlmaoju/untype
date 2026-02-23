"""Speech-to-text engine — local (faster-whisper) and API (OpenAI-compatible)."""

from __future__ import annotations

import io
import logging
import wave

import httpx
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local STT engine (faster-whisper)
# ---------------------------------------------------------------------------


class STTEngine:
    """Low-latency local STT engine with preloaded Whisper model."""

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "zh",
        beam_size: int = 5,
        vad_filter: bool = True,
        vad_threshold: float = 0.3,
    ):
        from faster_whisper import WhisperModel

        if device == "auto":
            device = self._detect_device()
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        logger.info(
            "Loading Whisper model %s on %s (%s)...",
            model_size, device, compute_type,
        )

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._language = language
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._vad_threshold = vad_threshold

        logger.info("Whisper model loaded successfully.")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio buffer to text."""
        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=self._vad_filter,
            vad_parameters={"threshold": self._vad_threshold},
        )
        text = "".join(segment.text for segment in segments)
        logger.info("Transcription (%s, %.2fs): %s", info.language, info.duration, text)
        return text

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"


# ---------------------------------------------------------------------------
# API STT engine (OpenAI-compatible /audio/transcriptions)
# ---------------------------------------------------------------------------


class STTApiEngine:
    """STT via OpenAI-compatible audio transcription API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        language: str = "zh",
        sample_rate: int = 16000,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
        )
        logger.info("STT API engine ready (%s, model=%s)", self._base_url, self._model)

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio buffer to text via API."""
        wav_bytes = self._audio_to_wav(audio)

        response = None
        try:
            response = self._client.post(
                f"{self._base_url}/audio/transcriptions",
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"model": self._model, "language": self._language},
            )
            response.raise_for_status()
            data = response.json()
            text = data["text"]
            logger.info("API transcription: %s", text)
            return text
        except httpx.HTTPStatusError as exc:
            logger.error("STT API HTTP error %s: %s", exc.response.status_code, exc.response.text)
            raise
        except (KeyError, ValueError) as exc:
            body = response.text[:500] if response is not None and response.text else "(empty)"
            logger.error("Malformed STT API response (body: %s): %s", body, exc)
            raise
        except httpx.TimeoutException as exc:
            logger.error("STT API request timed out: %s", exc)
            raise

    def close(self) -> None:
        self._client.close()

    @property
    def is_loaded(self) -> bool:
        return True

    def _audio_to_wav(self, audio: np.ndarray) -> bytes:
        """Convert Float32 numpy audio to in-memory WAV bytes."""
        pcm16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm16.tobytes())
        return buf.getvalue()
