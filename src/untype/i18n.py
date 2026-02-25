"""Internationalization (i18n) module — JSON-based locale support.

Language packs are stored as JSON files in the ``locales/`` directory.
Users can add their own translations by placing ``<lang>.json`` files there.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Built-in fallback translations (used when no locale files exist)
_FALLBACK: dict[str, str] = {
    "app.name": "UnType",
    "tray.status.ready": "Ready",
    "tray.status.recording": "Recording...",
    "tray.status.transcribing": "Transcribing...",
    "tray.status.processing": "Processing...",
    "tray.status.error": "Error",
    "tray.settings": "Settings...",
    "tray.personas": "Personas...",
    "tray.quit": "Quit",
}

# Current translations (loaded from JSON)
_translations: dict[str, str] = {}

# Current language code
_current_lang: str = "zh"


def get_locales_dir() -> Path:
    """Return the path to the locales directory.

    In development: ``<project_root>/locales/`` (next to ``src/``).
    When frozen (PyInstaller): check two locations:
        1. Next to the .exe (user-customizable, takes priority)
        2. Inside _internal/ (bundled defaults)
    """
    import sys

    if getattr(sys, "frozen", False):
        # PyInstaller: prefer user-customizable location next to .exe
        exe_dir = Path(sys.executable).parent
        user_locales = exe_dir / "locales"
        if user_locales.is_dir():
            return user_locales
        # Fall back to bundled location inside _internal/
        return exe_dir / "_internal" / "locales"
    # Development: project root (src/untype/i18n.py → ../../../locales)
    return Path(__file__).resolve().parent.parent.parent / "locales"


def list_available_locales() -> list[str]:
    """Return a list of available locale codes (e.g. ``['en', 'zh']``).

    Each locale corresponds to a ``<code>.json`` file in the locales directory.
    Returns an empty list if the directory does not exist.
    """
    locales_dir = get_locales_dir()
    if not locales_dir.is_dir():
        return []
    return sorted(p.stem for p in locales_dir.glob("*.json"))


def get_locale_display_name(lang: str) -> str:
    """Return the display name for a locale code (e.g. 'zh' → '简体中文')."""
    # Try to get from the locale file's meta section
    data = load_locale(lang)
    if data and "meta" in data and "name" in data["meta"]:
        return data["meta"]["name"]
    # Fallback to built-in names
    builtin_names = {"zh": "简体中文", "en": "English"}
    return builtin_names.get(lang, lang)


def load_locale(lang: str) -> dict[str, Any] | None:
    """Load a locale JSON file.

    Returns ``None`` if the file does not exist or cannot be parsed.
    """
    path = get_locales_dir() / f"{lang}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load locale %s: %s", lang, exc)
        return None


def set_language(lang: str) -> bool:
    """Switch to a new language.

    Returns ``True`` if the language was successfully loaded,
    ``False`` if the locale file was not found.
    """
    global _current_lang, _translations

    if lang == _current_lang and _translations:
        return True

    data = load_locale(lang)
    if data is None:
        logger.warning("Locale '%s' not found, keeping current language", lang)
        return False

    _translations = data.get("translations", {})
    _current_lang = lang
    logger.info("Language switched to '%s'", lang)
    return True


def init_language(lang: str) -> None:
    """Initialize the i18n system on startup.

    Attempts to load the requested language, falling back to 'zh' if not found,
    and finally to the built-in fallback if no locale files exist.
    """
    global _translations, _current_lang

    if set_language(lang):
        return

    # Try default Chinese
    if lang != "zh" and set_language("zh"):
        _current_lang = "zh"
        return

    # No locale files at all — use built-in fallback
    _translations = _FALLBACK.copy()
    _current_lang = "en"  # Fallback is in English
    logger.warning("No locale files found, using built-in English fallback")


def get_language() -> str:
    """Return the current language code."""
    return _current_lang


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    """Return the translated string for ``key``.

    If the key is not found in the current locale:
    1. Return ``default`` if provided
    2. Fall back to the built-in fallback
    3. Return the key itself

    Additional keyword arguments can be used for string formatting:
        t("persona.import_success", count=3) → "已导入 3 个人格。"
    """
    # Try current locale
    if key in _translations:
        text = _translations[key]
    elif default is not None:
        text = default
    elif key in _FALLBACK:
        text = _FALLBACK[key]
    else:
        text = key

    # Apply formatting if kwargs provided
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            pass  # Missing placeholder, return as-is

    return text
