"""System tray icon with settings dialog and status display."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

import pystray
from PIL import Image, ImageDraw

from untype.config import AppConfig, save_config
from untype.i18n import get_locale_display_name, list_available_locales, t

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Icon colours for each application state
# ---------------------------------------------------------------------------

_STATUS_COLORS: dict[str, str] = {
    "Ready": "#4CAF50",  # green
    "Recording...": "#FF9800",  # orange
    "Transcribing...": "#2196F3",  # blue
    "Processing...": "#9C27B0",  # purple
    "Error": "#F44336",  # red
}

# Translation keys for status text
_STATUS_KEYS: dict[str, str] = {
    "Ready": "tray.status.ready",
    "Recording...": "tray.status.recording",
    "Transcribing...": "tray.status.transcribing",
    "Processing...": "tray.status.processing",
    "Error": "tray.status.error",
}

_DEFAULT_ICON_COLOR = "#4CAF50"


# ---------------------------------------------------------------------------
# Icon helper
# ---------------------------------------------------------------------------


def _create_icon_image(color: str = _DEFAULT_ICON_COLOR, size: int = 64) -> Image.Image:
    """Create a simple colored circle icon on a transparent background."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    return image


# ---------------------------------------------------------------------------
# Settings dialog (tkinter)
# ---------------------------------------------------------------------------


class SettingsDialog:
    """Tkinter settings dialog for editing the UnType configuration.

    Because tkinter is *not* thread-safe, the dialog creates its own
    :class:`tkinter.Tk` root (hidden) and runs a local mainloop on the
    calling thread.  Callers should invoke :meth:`show` from a dedicated
    thread — **never** from the pystray callback thread directly.
    """

    def __init__(self, config: AppConfig, on_save: Callable[[AppConfig], None]) -> None:
        """
        Args:
            config: Current app configuration.
            on_save: Callback invoked when the user clicks *Save*;
                     receives the updated :class:`AppConfig`.
        """
        self._config = config
        self._on_save = on_save

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    def show(self) -> None:
        """Show the settings dialog (blocks until closed)."""
        root = tk.Tk()
        root.title(t("settings.title"))
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # Ensure the window appears in front and grabs focus
        root.after(100, lambda: root.attributes("-topmost", False))

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        row = 0

        # -- Hotkey -------------------------------------------------------
        row = self._heading(frame, t("settings.heading.hotkey"), row)
        hotkey_var = self._text_field(
            root,
            frame,
            t("settings.trigger"),
            self._config.hotkey.trigger,
            row,
        )
        row += 1
        # Mode combo with translated options
        mode_options = ["toggle", "hold"]
        mode_labels = [t("settings.mode.toggle"), t("settings.mode.hold")]
        hotkey_mode_var = self._combo_field(
            root,
            frame,
            t("settings.mode"),
            self._config.hotkey.mode,
            mode_options,
            row,
            labels=mode_labels,
        )
        row += 1

        # -- LLM ----------------------------------------------------------
        row = self._heading(frame, t("settings.heading.llm"), row)
        llm_url_var = self._text_field(
            root,
            frame,
            t("settings.base_url"),
            self._config.llm.base_url,
            row,
        )
        row += 1
        llm_key_var = self._text_field(
            root,
            frame,
            t("settings.api_key"),
            self._config.llm.api_key,
            row,
            show="*",
        )
        row += 1
        llm_model_var = self._text_field(
            root,
            frame,
            t("settings.model"),
            self._config.llm.model,
            row,
        )
        row += 1

        # -- STT -----------------------------------------------------------
        row = self._heading(frame, t("settings.heading.stt"), row)
        stt_backend_options = ["api", "local"]
        stt_backend_labels = [t("settings.backend.api"), t("settings.backend.local")]
        stt_backend_var = self._combo_field(
            root,
            frame,
            t("settings.backend"),
            self._config.stt.backend,
            stt_backend_options,
            row,
            labels=stt_backend_labels,
        )
        row += 1
        stt_api_url_var = self._text_field(
            root,
            frame,
            t("settings.stt_api_url"),
            self._config.stt.api_base_url,
            row,
        )
        row += 1
        stt_api_key_var = self._text_field(
            root,
            frame,
            t("settings.stt_api_key"),
            self._config.stt.api_key,
            row,
            show="*",
        )
        row += 1
        stt_api_model_var = self._text_field(
            root,
            frame,
            t("settings.stt_api_model"),
            self._config.stt.api_model,
            row,
        )
        row += 1
        stt_model_var = self._combo_field(
            root,
            frame,
            t("settings.local_model"),
            self._config.stt.model_size,
            ["small", "medium", "large-v3"],
            row,
        )
        row += 1
        stt_device_var = self._combo_field(
            root,
            frame,
            t("settings.local_device"),
            self._config.stt.device,
            ["auto", "cuda", "cpu"],
            row,
        )
        row += 1

        # -- Audio ---------------------------------------------------------
        row = self._heading(frame, t("settings.heading.audio"), row)
        gain_var = self._number_field(
            root,
            frame,
            t("settings.gain_boost"),
            self._config.audio.gain_boost,
            row,
        )
        row += 1

        # -- Overlay -------------------------------------------------------
        row = self._heading(frame, t("settings.heading.overlay"), row)
        capsule_pos_options = ["caret", "bottom_center", "bottom_left"]
        capsule_pos_labels = [
            t("settings.capsule_position.caret"),
            t("settings.capsule_position.bottom_center"),
            t("settings.capsule_position.bottom_left"),
        ]
        capsule_pos_var = self._combo_field(
            root,
            frame,
            t("settings.capsule_position"),
            self._config.overlay.capsule_position,
            capsule_pos_options,
            row,
            labels=capsule_pos_labels,
        )
        row += 1

        # -- Language ------------------------------------------------------
        row = self._heading(frame, t("settings.heading.language"), row)
        available_langs = list_available_locales() or ["zh"]
        lang_var = self._combo_field(
            root,
            frame,
            t("settings.language"),
            self._config.language,
            available_langs,
            row,
            labels=[get_locale_display_name(lang) for lang in available_langs],
        )
        row += 1

        # -- Save / Cancel -------------------------------------------------
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(16, 0), sticky="e")

        ttk.Button(btn_frame, text=t("settings.cancel"), command=root.destroy).pack(
            side="right",
            padx=(8, 0),
        )
        ttk.Button(
            btn_frame,
            text=t("settings.save"),
            command=lambda: self._do_save(
                root,
                hotkey_var=hotkey_var,
                hotkey_mode_var=hotkey_mode_var,
                llm_url_var=llm_url_var,
                llm_key_var=llm_key_var,
                llm_model_var=llm_model_var,
                stt_backend_var=stt_backend_var,
                stt_api_url_var=stt_api_url_var,
                stt_api_key_var=stt_api_key_var,
                stt_api_model_var=stt_api_model_var,
                stt_model_var=stt_model_var,
                stt_device_var=stt_device_var,
                gain_var=gain_var,
                capsule_pos_var=capsule_pos_var,
                lang_var=lang_var,
            ),
        ).pack(side="right")

        # Centre the window on screen
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"+{x}+{y}")

        root.mainloop()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _heading(parent: ttk.Frame, text: str, row: int) -> int:
        """Insert a bold section heading and return the *next* row index."""
        lbl = ttk.Label(parent, text=text, font=("TkDefaultFont", 10, "bold"))
        lbl.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 4))
        return row + 1

    @staticmethod
    def _text_field(
        master: tk.Tk,
        parent: ttk.Frame,
        label: str,
        value: str,
        row: int,
        *,
        show: str = "",
    ) -> tk.StringVar:
        """Add a labelled text entry and return the associated StringVar."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        var = tk.StringVar(master=master, value=value)
        entry = ttk.Entry(parent, textvariable=var, width=48)
        if show:
            entry.configure(show=show)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        return var

    @staticmethod
    def _combo_field(
        master: tk.Tk,
        parent: ttk.Frame,
        label: str,
        value: str,
        options: list[str],
        row: int,
        labels: list[str] | None = None,
    ) -> tk.StringVar:
        """Add a labelled dropdown and return the associated StringVar.

        Args:
            master: The Tk root.
            parent: Parent frame.
            label: Label text.
            value: Current value (should be one of ``options``).
            options: Internal option values.
            row: Grid row.
            labels: Optional display labels for options (same order as ``options``).
                    If provided, the dropdown shows labels but stores the option value.
        """
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        var = tk.StringVar(master=master, value=value)

        if labels is not None:
            # Use labels for display, but we need to handle mapping
            # Create a custom combobox that shows labels but stores values
            # Build a mapping from label to value
            label_to_value = dict(zip(labels, options))
            value_to_label = dict(zip(options, labels))

            # Set the display label as current value
            display_var = tk.StringVar(master=master, value=value_to_label.get(value, value))

            combo = ttk.Combobox(
                parent,
                textvariable=display_var,
                values=labels,
                width=45,
                state="readonly",
            )
            combo.grid(row=row, column=1, sticky="ew", pady=2)

            # When selection changes, update the internal var
            def _on_select(_event: tk.Event) -> None:  # type: ignore[type-arg]
                selected_label = display_var.get()
                var.set(label_to_value.get(selected_label, selected_label))

            combo.bind("<<ComboboxSelected>>", _on_select)
        else:
            combo = ttk.Combobox(
                parent, textvariable=var, values=options, width=45, state="readonly"
            )
            combo.grid(row=row, column=1, sticky="ew", pady=2)

        return var

    @staticmethod
    def _number_field(
        master: tk.Tk,
        parent: ttk.Frame,
        label: str,
        value: float,
        row: int,
    ) -> tk.DoubleVar:
        """Add a labelled numeric entry and return the associated DoubleVar."""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        var = tk.DoubleVar(master=master, value=value)
        ttk.Entry(parent, textvariable=var, width=48).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=2,
        )
        return var

    # ------------------------------------------------------------------ #

    def _do_save(
        self,
        root: tk.Tk,
        *,
        hotkey_var: tk.StringVar,
        hotkey_mode_var: tk.StringVar,
        llm_url_var: tk.StringVar,
        llm_key_var: tk.StringVar,
        llm_model_var: tk.StringVar,
        stt_backend_var: tk.StringVar,
        stt_api_url_var: tk.StringVar,
        stt_api_key_var: tk.StringVar,
        stt_api_model_var: tk.StringVar,
        stt_model_var: tk.StringVar,
        stt_device_var: tk.StringVar,
        gain_var: tk.DoubleVar,
        capsule_pos_var: tk.StringVar,
        lang_var: tk.StringVar,
    ) -> None:
        """Collect values from the dialog, persist, and notify the app."""
        import tkinter.messagebox as messagebox

        try:
            gain_value = gain_var.get()
        except Exception:
            messagebox.showerror(t("settings.error.invalid_gain"), t("settings.error.invalid_gain"))
            return

        # Apply changes to config
        self._config.hotkey.trigger = hotkey_var.get().strip()
        self._config.hotkey.mode = hotkey_mode_var.get().strip()
        self._config.llm.base_url = llm_url_var.get().strip()
        self._config.llm.api_key = llm_key_var.get().strip()
        self._config.llm.model = llm_model_var.get().strip()
        self._config.stt.backend = stt_backend_var.get().strip()
        self._config.stt.api_base_url = stt_api_url_var.get().strip()
        self._config.stt.api_key = stt_api_key_var.get().strip()
        self._config.stt.api_model = stt_api_model_var.get().strip()
        self._config.stt.model_size = stt_model_var.get().strip()
        self._config.stt.device = stt_device_var.get().strip()
        self._config.audio.gain_boost = gain_value
        self._config.overlay.capsule_position = capsule_pos_var.get().strip()
        self._config.language = lang_var.get().strip()

        try:
            save_config(self._config)
            logger.info("Configuration saved")
        except Exception:
            logger.exception("Failed to save configuration")
            messagebox.showerror("Error", t("settings.error.save_failed"))
            return

        root.destroy()

        try:
            self._on_save(self._config)
        except Exception:
            logger.exception("Error in on_save callback")


# ---------------------------------------------------------------------------
# System tray application
# ---------------------------------------------------------------------------


class TrayApp:
    """System tray application manager.

    Provides a pystray-based tray icon with a right-click context menu
    showing the current status, a link to the settings dialog, and a quit
    action.
    """

    def __init__(
        self,
        config: AppConfig,
        on_settings_changed: Callable[[AppConfig], None],
        on_quit: Callable[[], None],
        on_personas_changed: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._on_settings_changed = on_settings_changed
        self._on_quit = on_quit
        self._on_personas_changed_cb = on_personas_changed
        self._status: str = "Ready"
        self._icon: pystray.Icon | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Run the system tray icon (**blocks** the calling thread)."""
        self._icon = pystray.Icon(
            name="UnType",
            icon=_create_icon_image(_STATUS_COLORS.get(self._status, _DEFAULT_ICON_COLOR)),
            title=f"UnType - {self._status}",
            menu=self._build_menu(),
        )
        logger.info("Starting system tray icon")
        self._icon.run()

    def update_status(self, status: str) -> None:
        """Update the status text and icon colour shown in the tray."""
        self._status = status
        icon = self._icon
        if icon is None:
            return

        color = _STATUS_COLORS.get(status, _DEFAULT_ICON_COLOR)
        icon.icon = _create_icon_image(color)

        # Translate status for display
        status_key = _STATUS_KEYS.get(status, "tray.status.ready")
        translated_status = t(status_key)
        icon.title = f"{t('app.name')} - {translated_status}"

        # Rebuild the menu so the status line reflects the new state.
        icon.menu = self._build_menu()
        icon.update_menu()
        logger.debug("Tray status updated to %r", status)

    def stop(self) -> None:
        """Stop the tray icon and unblock :meth:`run`."""
        icon = self._icon
        if icon is not None:
            icon.stop()
            logger.info("System tray icon stopped")

    # ------------------------------------------------------------------ #
    # Menu construction
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> pystray.Menu:
        """Build the right-click context menu."""
        # Translate status text
        status_key = _STATUS_KEYS.get(self._status, "tray.status.ready")
        translated_status = t(status_key)
        return pystray.Menu(
            pystray.MenuItem(
                f"{t('app.name')} - {translated_status}",
                action=None,
                enabled=False,
            ),
            pystray.MenuItem(
                t("tray.settings"),
                self._on_settings_clicked,
            ),
            pystray.MenuItem(
                t("tray.personas"),
                self._on_personas_clicked,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                t("tray.quit"),
                self._on_quit_clicked,
            ),
        )

    # ------------------------------------------------------------------ #
    # Menu action handlers
    # ------------------------------------------------------------------ #

    def _on_settings_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Open the settings dialog on a dedicated thread."""
        thread = threading.Thread(
            target=self._show_settings_dialog,
            name="untype-settings-dialog",
            daemon=True,
        )
        thread.start()

    def _on_personas_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Open the persona manager dialog on a dedicated thread."""
        threading.Thread(
            target=self._show_persona_dialog,
            name="untype-persona-dialog",
            daemon=True,
        ).start()

    def _show_persona_dialog(self) -> None:
        """Create and show the persona manager dialog (runs on its own thread)."""
        try:
            from untype.persona_dialog import PersonaManagerDialog

            dialog = PersonaManagerDialog(on_changed=self._on_personas_changed_cb)
            dialog.show()
        except Exception:
            logger.exception("Failed to open persona manager dialog")

    def _show_settings_dialog(self) -> None:
        """Create and show the settings dialog (runs on its own thread)."""
        try:
            dialog = SettingsDialog(self._config, self._on_settings_saved)
            dialog.show()
        except Exception:
            logger.exception("Failed to open settings dialog")

    def _on_settings_saved(self, config: AppConfig) -> None:
        """Handle a successful save from the settings dialog."""
        self._config = config
        try:
            self._on_settings_changed(config)
        except Exception:
            logger.exception("Error in on_settings_changed callback")

    def _on_quit_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """Handle the Quit menu item."""
        logger.info("Quit requested via tray menu")
        try:
            self._on_quit()
        except Exception:
            logger.exception("Error in on_quit callback")
        self.stop()
