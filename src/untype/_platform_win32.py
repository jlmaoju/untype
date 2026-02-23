"""Windows implementation of platform-specific operations (ctypes + user32)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import tkinter as tk

from pynput.keyboard import Key

from untype.platform import CaretPosition, WindowIdentity

# ---------------------------------------------------------------------------
# ctypes structures
# ---------------------------------------------------------------------------

user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.wintypes.LONG), ("y", ctypes.wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.wintypes.LONG),
        ("top", ctypes.wintypes.LONG),
        ("right", ctypes.wintypes.LONG),
        ("bottom", ctypes.wintypes.LONG),
    ]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("hwndActive", ctypes.wintypes.HWND),
        ("hwndFocus", ctypes.wintypes.HWND),
        ("hwndCapture", ctypes.wintypes.HWND),
        ("hwndMenuOwner", ctypes.wintypes.HWND),
        ("hwndMoveSize", ctypes.wintypes.HWND),
        ("hwndCaret", ctypes.wintypes.HWND),
        ("rcCaret", RECT),
    ]


# ---------------------------------------------------------------------------
# Caret position
# ---------------------------------------------------------------------------


def get_caret_screen_position() -> CaretPosition:
    """Return the screen position of the text caret.

    Tries ``GetGUIThreadInfo`` + ``ClientToScreen`` first.  If the target
    application doesn't expose a Win32 caret (common with modern apps), falls
    back to the current mouse cursor position.
    """
    # Try GetGUIThreadInfo for the foreground thread.
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, None)

    gui = GUITHREADINFO()
    gui.cbSize = ctypes.sizeof(GUITHREADINFO)

    if user32.GetGUIThreadInfo(tid, ctypes.byref(gui)) and gui.hwndCaret:
        pt = POINT(gui.rcCaret.left, gui.rcCaret.top)
        user32.ClientToScreen(gui.hwndCaret, ctypes.byref(pt))
        return CaretPosition(x=pt.x, y=pt.y, found=True)

    # Fallback: mouse cursor position.
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return CaretPosition(x=pt.x, y=pt.y, found=False)


# ---------------------------------------------------------------------------
# Window tracking (Phase 2)
# ---------------------------------------------------------------------------


def get_foreground_window() -> WindowIdentity:
    """Take a snapshot of the current foreground window (HWND + PID + title)."""
    hwnd = user32.GetForegroundWindow()

    # Window title.
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # Process ID.
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    return WindowIdentity(hwnd=hwnd, title=title, pid=pid.value)


def verify_foreground_window(identity: WindowIdentity) -> bool:
    """Check whether the current foreground window matches *identity*.

    Compares both the HWND and the PID to handle the (rare) case where a
    window handle is reused by the OS for a different process.
    """
    current = get_foreground_window()
    return current.hwnd == identity.hwnd and current.pid == identity.pid


# ---------------------------------------------------------------------------
# Window styles (no-focus overlay)
# ---------------------------------------------------------------------------

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

GetWindowLongW = user32.GetWindowLongW
SetWindowLongW = user32.SetWindowLongW


def set_window_noactivate(tk_root: tk.Tk | tk.Toplevel) -> None:
    """Apply ``WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`` to a tkinter window.

    This prevents the overlay from stealing focus when it appears and hides
    it from the taskbar / Alt+Tab list.
    """
    # Ensure the window has been realized so it has an HWND.
    tk_root.update_idletasks()
    hwnd = int(tk_root.wm_frame(), 16)

    style = GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    SetWindowLongW(hwnd, GWL_EXSTYLE, style)


# ---------------------------------------------------------------------------
# Platform key
# ---------------------------------------------------------------------------


def get_modifier_key() -> Key:
    """Return the primary modifier key for keyboard shortcuts (Ctrl on Windows)."""
    return Key.ctrl_l
