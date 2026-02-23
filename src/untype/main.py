"""Main entry point — orchestrates all UnType modules together."""

from __future__ import annotations

import copy
import logging
import threading
import time

import pyperclip

from untype.audio import AudioRecorder, normalize_audio
from untype.clipboard import grab_selected_text, inject_text
from untype.config import AppConfig, Persona, load_config, load_personas, save_config
from untype.hotkey import HotkeyListener
from untype.llm import LLMClient
from untype.overlay import CapsuleOverlay
from untype.platform import (
    WindowIdentity,
    get_caret_screen_position,
    get_foreground_window,
    verify_foreground_window,
)
from untype.stt import STTApiEngine, STTEngine
from untype.tray import TrayApp

logger = logging.getLogger(__name__)


class UnTypeApp:
    """Main application orchestrator.

    Wires together the hotkey listener, audio recorder, STT engine, LLM
    client, and system tray icon into a push-to-talk pipeline.
    """

    def __init__(self) -> None:
        logger.info("Loading configuration...")
        self._config = load_config()
        # Deep copy so settings-change detection works (the dialog mutates in-place)
        self._prev_config = copy.deepcopy(self._config)

        # -- Persona system -----------------------------------------------
        self._personas: list[Persona] = load_personas()
        if self._personas:
            logger.info(
                "Loaded %d persona(s): %s",
                len(self._personas),
                ", ".join(p.name for p in self._personas),
            )

        # -- Interaction state (written in on_press, read in pipeline) --------
        self._mode: str = "insert"  # "polish" or "insert"
        self._selected_text: str | None = None
        self._original_clipboard: str | None = None

        # -- HWND safety (Phase 2) --------------------------------------------
        self._target_window: WindowIdentity | None = None
        self._held_result: str | None = None
        self._held_clipboard: str | None = None
        self._window_mismatch: bool = False
        self._hwnd_watch_active: bool = False
        self._caret_x: int = 0
        self._caret_y: int = 0

        # -- Pipeline lock: only one interaction at a time --------------------
        self._pipeline_lock = threading.Lock()
        # True only when _on_hotkey_press succeeded (lock acquired)
        self._press_active = False
        # Signalled once the press-setup thread finishes (recording started or error)
        self._recording_started = threading.Event()
        self._recording_started.set()  # initially "done"

        # -- Initialise subsystems -------------------------------------------
        logger.info("Initialising audio recorder...")
        self._recorder = self._init_recorder()

        logger.info("Initialising STT engine (this may take a moment)...")
        self._stt = self._init_stt()

        logger.info("Initialising LLM client...")
        self._llm: LLMClient | None = self._init_llm_client()

        logger.info("Initialising hotkey listener...")
        self._hotkey = HotkeyListener(
            self._config.hotkey.trigger,
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )

        logger.info("Initialising system tray...")
        self._tray = TrayApp(
            config=self._config,
            on_settings_changed=self._on_settings_changed,
            on_quit=self._on_quit,
        )

        logger.info("Initialising overlay...")
        self._overlay = CapsuleOverlay(
            on_hold_inject=self._on_hold_inject,
            on_hold_copy=self._on_hold_copy,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the application.

        Starts the hotkey listener, then runs the system-tray icon which
        blocks until the user quits.
        """
        self._hotkey.start()
        self._overlay.start()
        logger.info("UnType is ready.  Hold %s to speak.", self._config.hotkey.trigger)
        self._tray.update_status("Ready")

        # tray.run() blocks until the user selects Quit.
        self._tray.run()

    # ------------------------------------------------------------------
    # Hotkey callbacks
    # ------------------------------------------------------------------

    def _on_hotkey_press(self) -> None:
        """Called when the push-to-talk hotkey is pressed.

        IMPORTANT: This runs inside the pynput low-level keyboard hook
        callback.  On Windows the hook has a strict timeout (~300 ms).
        If we block too long here, Windows removes the hook and the
        hotkey listener dies silently.  Therefore we only acquire the
        pipeline lock and immediately spawn a worker thread for the
        heavy clipboard-probe + recording-start work.
        """
        if not self._pipeline_lock.acquire(blocking=False):
            logger.warning("Pipeline already running — ignoring hotkey press")
            return

        # Safety net: if there's a held result from a previous HWND mismatch,
        # copy it to clipboard before discarding so the user doesn't lose it.
        if self._held_result is not None:
            logger.info("Discarding held result to clipboard before new interaction")
            try:
                pyperclip.copy(self._held_result)
            except Exception:
                pass
            self._held_result = None
            self._held_clipboard = None
            self._overlay.hide_hold_bubble()

        self._press_active = True
        self._recording_started.clear()
        threading.Thread(
            target=self._start_recording, name="untype-rec-start", daemon=True,
        ).start()

    def _on_hotkey_release(self) -> None:
        """Called when the push-to-talk hotkey is released.

        Spawns a background thread to run the rest of the pipeline so that
        the hotkey listener is not blocked.
        """
        if not self._press_active:
            return
        self._press_active = False
        threading.Thread(
            target=self._process_pipeline, name="untype-pipeline", daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Recording start (runs on a worker thread, NOT the hook thread)
    # ------------------------------------------------------------------

    def _start_recording(self) -> None:
        """Probe the clipboard and start the microphone.

        This is spawned by :meth:`_on_hotkey_press` on a short-lived worker
        thread so the keyboard hook callback returns immediately.  The
        ``_recording_started`` event is set in the ``finally`` block to let
        the pipeline thread know it can proceed.
        """
        try:
            # Phase 2: capture the target window HWND before anything else.
            self._target_window = get_foreground_window()
            logger.info(
                "Target window: %r (HWND=%d, PID=%d)",
                self._target_window.title,
                self._target_window.hwnd,
                self._target_window.pid,
            )

            # Get caret position for overlay placement.
            caret = get_caret_screen_position()
            self._caret_x = caret.x
            self._caret_y = caret.y
            logger.info(
                "Caret position: (%d, %d) found=%s",
                caret.x, caret.y, caret.found,
            )

            self._tray.update_status("Listening...")
            self._overlay.show(self._caret_x, self._caret_y, "Listening...")

            # Grab selected text to determine the interaction mode.
            logger.info("Grabbing selected text...")
            self._selected_text, self._original_clipboard = grab_selected_text()

            if self._selected_text:
                self._mode = "polish"
                logger.info("Mode: polish (selected %d chars)", len(self._selected_text))
            else:
                self._mode = "insert"
                logger.info("Mode: insert (no selection detected)")

            # Start recording.
            logger.info("Starting audio recording...")
            self._recorder.start()
            self._tray.update_status("Recording...")
            self._overlay.update_status("Recording...")

            # Start continuous HWND monitoring.
            self._start_hwnd_watcher()
        except Exception:
            logger.exception("Error starting recording")
            self._tray.update_status("Error")
            self._overlay.update_status("Error")
        finally:
            # Always signal so the pipeline thread never hangs.
            self._recording_started.set()

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _process_pipeline(self) -> None:
        """Run the full STT -> staging -> (optional LLM) -> inject pipeline."""
        try:
            # Wait for the recording-start thread to finish its work.
            self._recording_started.wait(timeout=10.0)

            if not self._recorder.is_recording:
                logger.warning("Recording not active — aborting pipeline")
                self._tray.update_status("Ready")
                self._overlay.hide()
                return

            # 1. Stop recording and retrieve audio.
            logger.info("Stopping audio recording...")
            audio = self._recorder.stop()

            if audio.size == 0:
                logger.warning("Empty audio buffer — aborting pipeline")
                self._tray.update_status("Ready")
                self._overlay.hide()
                return

            # 2. Normalize audio (amplify whispered speech).
            self._tray.update_status("Transcribing...")
            self._overlay.update_status("Transcribing...")
            logger.info("Normalising audio (gain=%.1f)...", self._config.audio.gain_boost)
            audio = normalize_audio(audio, self._config.audio.gain_boost)

            # 3. Transcribe.
            logger.info("Transcribing audio...")
            text = self._stt.transcribe(audio)
            text = text.strip()

            if not text:
                logger.warning("Empty transcription — aborting pipeline")
                self._tray.update_status("Ready")
                self._overlay.hide()
                return

            logger.info("Transcription: %s", text)

            # 4. Stop HWND watcher and show staging area.
            self._hwnd_watch_active = False
            at_corner = self._window_mismatch
            self._tray.update_status("Ready")

            persona_tuples = [(p.id, p.icon, p.name) for p in self._personas[:3]]

            if at_corner:
                self._overlay.show_staging(
                    text, 0, 0, at_corner=True,
                    personas=persona_tuples or None,
                )
            else:
                self._overlay.show_staging(
                    text, self._caret_x, self._caret_y,
                    personas=persona_tuples or None,
                )

            # 5. Block until the user acts (Enter / Shift+Enter / Esc).
            edited_text, action = self._overlay.wait_staging()

            if action == "cancel":
                logger.info("Staging cancelled by user")
                return

            # Brief delay for focus to return to the previous window.
            time.sleep(0.15)

            if action == "raw":
                # Inject raw text directly (bypass LLM).
                logger.info("Injecting raw text (%d chars)", len(edited_text))
                inject_text(edited_text, self._original_clipboard)
                return

            # 6. action == "refine" or "persona:<id>" — send through LLM.
            # Do NOT re-capture target window here — keep the original one
            # from hotkey-press time so HWND safety works correctly even if
            # the user switched windows while the staging area was open.
            caret = get_caret_screen_position()
            self._overlay.show(caret.x, caret.y, "Processing...")
            self._tray.update_status("Processing...")

            # Restart HWND monitoring during the LLM call so that window
            # switches are caught both before and during LLM processing.
            self._start_hwnd_watcher()

            # Determine persona (if any).
            persona: Persona | None = None
            if action.startswith("persona:"):
                persona_id = action.split(":", 1)[1]
                persona = next(
                    (p for p in self._personas if p.id == persona_id), None,
                )

            result = self._run_llm(edited_text, persona=persona)

            # 7. Stop watcher and verify window before injection.
            self._hwnd_watch_active = False
            if self._target_window is not None and (
                self._window_mismatch
                or not verify_foreground_window(self._target_window)
            ):
                logger.warning(
                    "Window changed during LLM processing — holding result",
                )
                self._held_result = result
                self._held_clipboard = self._original_clipboard
                self._overlay.fly_to_hold_bubble(result)
                self._tray.update_status("Ready")
                return

            # 8. Inject refined result.
            logger.info("Injecting refined text (%d chars)", len(result))
            inject_text(result, self._original_clipboard)
            self._overlay.hide()
            self._tray.update_status("Ready")
            logger.info("Pipeline complete")

        except Exception:
            logger.exception("Pipeline error")
            self._hwnd_watch_active = False
            self._tray.update_status("Error")
            self._overlay.update_status("Error")
            # Briefly show the error status, then revert to Ready.
            time.sleep(2)
            self._tray.update_status("Ready")
            self._overlay.hide()
        finally:
            self._hwnd_watch_active = False
            self._pipeline_lock.release()

    def _run_llm(self, transcribed_text: str, persona: Persona | None = None) -> str:
        """Send transcribed text through the LLM, falling back to raw text.

        If *persona* is provided, its prompt/model/temperature/max_tokens
        overrides are passed to the LLM client for this single call.
        """
        if self._llm is None:
            logger.warning("LLM not configured — using raw transcription")
            return transcribed_text

        # Build per-call overrides from persona.
        overrides: dict = {}
        if persona:
            if self._mode == "polish" and persona.prompt_polish:
                overrides["system_prompt"] = persona.prompt_polish
            elif self._mode == "insert" and persona.prompt_insert:
                overrides["system_prompt"] = persona.prompt_insert
            if persona.model:
                overrides["model"] = persona.model
            if persona.temperature is not None:
                overrides["temperature"] = persona.temperature
            if persona.max_tokens is not None:
                overrides["max_tokens"] = persona.max_tokens

        try:
            if self._mode == "polish":
                logger.info("Polishing selected text with LLM...")
                return self._llm.polish(
                    self._selected_text or "", transcribed_text, **overrides,
                )
            else:
                logger.info("Inserting text via LLM...")
                return self._llm.insert(transcribed_text, **overrides)
        except Exception:
            logger.exception("LLM request failed — falling back to raw transcription")
            return transcribed_text

    # ------------------------------------------------------------------
    # HWND watcher (Phase 2 — polls foreground window during pipeline)
    # ------------------------------------------------------------------

    def _start_hwnd_watcher(self) -> None:
        """Begin polling the foreground window on a daemon thread."""
        self._window_mismatch = False
        self._hwnd_watch_active = True
        threading.Thread(
            target=self._watch_hwnd,
            name="untype-hwnd-watch",
            daemon=True,
        ).start()

    def _watch_hwnd(self) -> None:
        """Poll foreground window every 200ms.  Triggers capsule flight on mismatch."""
        while self._hwnd_watch_active:
            time.sleep(0.2)
            if not self._hwnd_watch_active:
                break
            if self._target_window is not None and not verify_foreground_window(
                self._target_window
            ):
                self._window_mismatch = True
                logger.info(
                    "Window switch detected during pipeline "
                    "(expected HWND=%d, title=%r)",
                    self._target_window.hwnd,
                    self._target_window.title,
                )
                self._overlay.fly_to_corner()
                break

    # ------------------------------------------------------------------
    # Hold callbacks (Phase 2 — called from overlay thread)
    # ------------------------------------------------------------------

    def _on_hold_inject(self) -> None:
        """Left-click on hold bubble — inject into the current foreground window."""
        result = self._held_result
        clipboard = self._held_clipboard
        self._held_result = None
        self._held_clipboard = None

        if result is None:
            return

        logger.info("Hold-inject: injecting %d chars into current window", len(result))
        inject_text(result, clipboard)

    def _on_hold_copy(self) -> None:
        """Right-click on hold bubble — copy held text to clipboard."""
        result = self._held_result
        self._held_result = None
        self._held_clipboard = None

        if result is None:
            return

        logger.info("Hold-copy: copying %d chars to clipboard", len(result))
        try:
            pyperclip.copy(result)
        except Exception:
            logger.exception("Failed to copy held result to clipboard")

    # ------------------------------------------------------------------
    # Settings hot-reload
    # ------------------------------------------------------------------

    def _on_settings_changed(self, new_config: AppConfig) -> None:
        """Handle settings changes pushed from the tray settings dialog."""
        old = self._prev_config
        self._config = new_config
        self._prev_config = copy.deepcopy(new_config)

        logger.info("Saving updated configuration...")
        save_config(new_config)

        # --- Hotkey ---
        if new_config.hotkey.trigger != old.hotkey.trigger:
            logger.info(
                "Hotkey changed from %r to %r — restarting listener",
                old.hotkey.trigger,
                new_config.hotkey.trigger,
            )
            self._hotkey.stop()
            self._hotkey = HotkeyListener(
                new_config.hotkey.trigger,
                on_press=self._on_hotkey_press,
                on_release=self._on_hotkey_release,
            )
            self._hotkey.start()

        # --- Audio recorder ---
        if (
            new_config.audio.sample_rate != old.audio.sample_rate
            or new_config.audio.device != old.audio.device
        ):
            logger.info("Audio settings changed — reinitialising recorder")
            self._recorder = self._init_recorder()

        # --- STT engine ---
        stt_changed = (
            new_config.stt.backend != old.stt.backend
            or new_config.stt.model_size != old.stt.model_size
            or new_config.stt.device != old.stt.device
            or new_config.stt.compute_type != old.stt.compute_type
            or new_config.stt.api_base_url != old.stt.api_base_url
            or new_config.stt.api_key != old.stt.api_key
            or new_config.stt.api_model != old.stt.api_model
        )
        if stt_changed:
            logger.info("STT settings changed — reinitialising engine...")
            old_stt = self._stt
            self._stt = self._init_stt()
            if isinstance(old_stt, STTApiEngine):
                old_stt.close()

        # --- LLM client ---
        llm_changed = (
            new_config.llm.base_url != old.llm.base_url
            or new_config.llm.api_key != old.llm.api_key
            or new_config.llm.model != old.llm.model
            or new_config.llm.temperature != old.llm.temperature
            or new_config.llm.max_tokens != old.llm.max_tokens
            or new_config.llm.prompts.polish != old.llm.prompts.polish
            or new_config.llm.prompts.insert != old.llm.prompts.insert
        )
        if llm_changed:
            logger.info("LLM settings changed — reinitialising client")
            if self._llm is not None:
                self._llm.close()
            self._llm = self._init_llm_client()

        # --- Personas ---
        self._personas = load_personas()
        logger.info("Reloaded %d persona(s)", len(self._personas))

        logger.info("Settings update complete")

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _on_quit(self) -> None:
        """Handle the Quit action from the tray menu."""
        logger.info("Shutting down...")
        self._hotkey.stop()
        self._overlay.stop()
        if self._llm is not None:
            self._llm.close()
        if isinstance(self._stt, STTApiEngine):
            self._stt.close()
        self._tray.stop()
        logger.info("Goodbye.")

    # ------------------------------------------------------------------
    # Module initialisation helpers
    # ------------------------------------------------------------------

    def _init_recorder(self) -> AudioRecorder:
        """Create an AudioRecorder from the current config."""
        device = self._config.audio.device or None  # "" -> None (system default)
        return AudioRecorder(
            sample_rate=self._config.audio.sample_rate,
            device=device,
        )

    def _init_stt(self) -> STTEngine | STTApiEngine:
        """Create an STT engine from the current config."""
        cfg = self._config.stt

        if cfg.backend == "api" and cfg.api_base_url and cfg.api_key:
            logger.info("Using API STT backend (%s)", cfg.api_model)
            return STTApiEngine(
                base_url=cfg.api_base_url,
                api_key=cfg.api_key,
                model=cfg.api_model,
                language=cfg.language,
                sample_rate=self._config.audio.sample_rate,
            )

        logger.info("Using local STT backend (model=%s)", cfg.model_size)
        return STTEngine(
            model_size=cfg.model_size,
            device=cfg.device,
            compute_type=cfg.compute_type,
            language=cfg.language,
            beam_size=cfg.beam_size,
            vad_filter=cfg.vad_filter,
            vad_threshold=cfg.vad_threshold,
        )

    def _init_llm_client(self) -> LLMClient | None:
        """Create an LLM client from config.

        Returns ``None`` if the LLM is not fully configured (missing
        base_url, api_key, or model), in which case pipeline steps that
        require the LLM will fall back to raw transcription output.
        """
        cfg = self._config.llm

        if not cfg.base_url or not cfg.api_key or not cfg.model:
            logger.warning(
                "LLM not fully configured (base_url=%r, api_key=%s, model=%r) "
                "— LLM processing will be skipped",
                cfg.base_url,
                "***" if cfg.api_key else "(empty)",
                cfg.model,
            )
            return None

        return LLMClient(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            prompts={
                "polish": cfg.prompts.polish,
                "insert": cfg.prompts.insert,
            },
        )


# ======================================================================
# Entry point
# ======================================================================


def main() -> None:
    """Entry point for the UnType application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    app = UnTypeApp()
    app.run()


if __name__ == "__main__":
    main()
