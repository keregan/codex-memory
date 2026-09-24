from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


CF_UNICODETEXT = 13


def read_clipboard_text() -> str:
    """Read Unicode text from the Windows clipboard without extra packages."""
    if sys.platform != "win32":
        raise RuntimeError("--clipboard is currently supported only on Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        raise RuntimeError("Не удалось открыть буфер обмена. Попробуйте скопировать текст ещё раз.")
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            raise ValueError("В буфере обмена нет текста")
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            raise RuntimeError("Не удалось получить текст из буфера обмена")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Не удалось прочитать текст из буфера обмена")
        try:
            text = ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    if not text.strip():
        raise ValueError("Буфер обмена содержит пустой текст")
    return text
