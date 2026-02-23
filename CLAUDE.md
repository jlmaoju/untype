# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**UnType** (忘言) is an open-source voice input tool for Windows. It captures speech via a headset microphone, transcribes it (via online API or local faster-whisper), refines/polishes the text through an LLM API, and injects the result at the current cursor position — all triggered by a single push-to-talk hotkey.

Core flow: `Hotkey → Clipboard probe → Push-to-Talk audio capture → STT (API or local) → LLM refinement → Clipboard inject + simulated paste`

Two operating modes determined automatically on trigger:
- **Selected-text polish mode** (选中润色): If text is selected (detected via Ctrl+C clipboard grab), the STT result + selected text are sent to the LLM for refinement.
- **Cursor insert mode** (光标处提炼插入): If no text is selected, the STT result alone is sent to the LLM, and the output is inserted at the cursor.

## Tech Stack

- **Language:** Python 3.11+
- **Package manager:** uv (pyproject.toml)
- **STT engines:** Dual-backend — online API (OpenAI-compatible `/audio/transcriptions`) or local faster-whisper (CTranslate2). Default: API mode with `gpt-4o-transcribe`.
- **LLM:** User-configured OpenAI-compatible API (any provider via custom base_url + api_key)
- **GUI:** pystray system tray icon + tkinter settings dialog
- **Platform:** Windows only (global hotkeys, clipboard, key simulation via pynput)

## Common Commands

```bash
# Setup
uv sync                          # Install all dependencies
uv run python -m untype          # Run the application
uv run untype                    # Run via entry point

# Development
uv run pytest                    # Run all tests
uv run pytest tests/test_foo.py  # Run a single test file
uv run pytest -k "test_name"     # Run a specific test by name
uv run ruff check src/           # Lint
uv run ruff format src/          # Format
```

## Architecture

```
src/untype/
├── __init__.py
├── main.py          # Entry point + UnTypeApp orchestrator: wires all modules, runs pipeline
├── config.py        # TOML config schema (dataclasses), load/save to ~/.untype/config.toml
├── hotkey.py        # Global push-to-talk hotkey listener (pynput), parse_hotkey() + HotkeyListener
├── clipboard.py     # Clipboard save/restore, grab_selected_text(), inject_text() via Ctrl+C/V sim
├── audio.py         # AudioRecorder (sounddevice InputStream), in-memory Float32, normalize_audio()
├── stt.py           # STTEngine (local faster-whisper) + STTApiEngine (OpenAI-compatible API)
├── llm.py           # LLMClient: OpenAI-compatible sync HTTP client (httpx), polish() + insert()
└── tray.py          # TrayApp (pystray icon) + SettingsDialog (tkinter), status color changes
```

**Data flow (single interaction cycle):**

1. `hotkey.py` detects trigger (default: F6 press)
2. `main.py` spawns a worker thread (to avoid blocking the Windows keyboard hook — see below)
3. Worker thread: `clipboard.py` saves current clipboard, sends Ctrl+C, checks for new text → determines mode
4. Worker thread: `audio.py` starts recording while hotkey is held (Push-to-Talk)
5. On hotkey release, pipeline thread waits for recording setup, then stops recording
6. `audio.normalize_audio()` amplifies speech with gain boost
7. `stt.py` transcribes buffer via API or local engine → text string
8. `llm.py` builds prompt (mode-dependent), calls API → refined text
9. `clipboard.py` `inject_text()` writes result to clipboard, simulates Ctrl+V, restores original clipboard

**Concurrency model:**
- Hotkey listener runs on a daemon thread (pynput `WH_KEYBOARD_LL` hook)
- **Critical:** Hotkey press callback must return within ~300ms or Windows silently removes the hook. All heavy work (clipboard probe, recording start) is offloaded to a worker thread via `_start_recording()`, synchronised with a `threading.Event` (`_recording_started`).
- Pipeline processing (`_process_pipeline`) runs on a daemon thread per interaction, waits for `_recording_started` event before proceeding
- `threading.Lock` (`_pipeline_lock`) prevents concurrent pipeline runs
- `_press_active` flag prevents orphaned pipeline threads when press fails to acquire lock
- System tray `run()` blocks the main thread

**Key design constraints:**
- Audio never touches disk — recorded as in-memory Float32 buffer, passed directly to STT engine
- STT model is preloaded into memory at startup (local mode) or API client is pre-configured (API mode)
- Clipboard state is always saved before and restored after injection (50-150ms delays)
- Before simulating Ctrl+C/V, `_release_all_modifiers()` sends key-up events for all modifier keys to prevent contamination from physically held keys
- LLM graceful degradation: if unconfigured or on error, raw STT text is used as fallback
- Settings hot-reload: `_prev_config = copy.deepcopy(config)` snapshot is used for change detection (the settings dialog mutates config in-place), modules are selectively re-initialized only when relevant config changes

## Configuration

Settings stored in `~/.untype/config.toml` (created with defaults on first run):

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `hotkey` | `trigger` | `f6` | Push-to-talk hotkey (single key or combo like `alt+space`) |
| `audio` | `sample_rate` | `16000` | Recording sample rate (Hz) |
| `audio` | `gain_boost` | `3.0` | Pre-STT gain multiplier for quiet speech |
| `audio` | `device` | `""` | Audio device (empty = system default) |
| `stt` | `backend` | `api` | `api` (online) or `local` (faster-whisper) |
| `stt` | `api_base_url` | `""` | OpenAI-compatible transcription API endpoint |
| `stt` | `api_key` | `""` | API key for online STT |
| `stt` | `api_model` | `gpt-4o-transcribe` | Online STT model name |
| `stt` | `model_size` | `small` | Local faster-whisper model (`small`/`medium`/`large-v3`) |
| `stt` | `device` | `auto` | Local model device: `auto`/`cuda`/`cpu` |
| `stt` | `compute_type` | `auto` | Local model compute: `auto`/`float16`/`int8`/`int8_float16` |
| `stt` | `language` | `zh` | Transcription language code |
| `stt` | `vad_threshold` | `0.3` | VAD sensitivity (local only; lower = catches quieter speech) |
| `llm` | `base_url` | `""` | OpenAI-compatible chat API endpoint |
| `llm` | `api_key` | `""` | API key |
| `llm` | `model` | `""` | Model name to request |
| `llm.prompts` | `polish`/`insert` | (built-in) | System prompts for each mode |

## Known Issues & Past Fixes

- **Windows keyboard hook timeout:** The pynput `WH_KEYBOARD_LL` hook callback must return within ~300ms. Originally `_on_hotkey_press` performed clipboard probe + recording start inline, causing the hook to be silently removed by Windows. Fixed by offloading to a worker thread with `threading.Event` synchronisation.
- **Stray character injection:** Simulating Ctrl+C while the user's hotkey modifiers are still physically held causes the OS to interpret it as Alt+Ctrl+C (or similar). Fixed by calling `_release_all_modifiers()` before every simulated hotkey. Further fixed by switching from combo hotkey (`alt+space`) to single key (`f6`) to avoid modifier conflicts entirely.
- **Settings change detection:** The tkinter SettingsDialog mutates the config object in-place, so comparing old vs new always showed equality. Fixed by storing `_prev_config = copy.deepcopy(config)` before opening the dialog.
- **LLM language mismatch:** LLM responses defaulted to English. Fixed by adding "Always respond in the same language" to both polish and insert system prompts.

## Key Dependencies

- `faster-whisper` — CTranslate2-based Whisper inference (local STT)
- `sounddevice` — PortAudio-based audio capture
- `numpy` — Audio buffer manipulation
- `pynput` — Global hotkey capture + keyboard simulation
- `pyperclip` — Clipboard access
- `httpx` — Sync HTTP client for LLM and STT API calls
- `pystray` + `Pillow` — System tray icon
- `tomli-w` — TOML config writing (reading uses stdlib `tomllib`)
