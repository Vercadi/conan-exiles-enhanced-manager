"""Conan Exiles Enhanced Manager entry point."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _enable_dpi_awareness() -> None:
    """Use native Windows DPI scaling where available."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _enable_dpi_awareness()

    from conan_manager.ui.app_window import AppWindow

    app = AppWindow()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        message = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Conan Exiles Enhanced Manager - Fatal Error", message)
            root.destroy()
        except Exception:
            print(message, file=sys.stderr)
        sys.exit(1)
