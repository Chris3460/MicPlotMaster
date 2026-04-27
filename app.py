import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui_desktop.main_window import MainWindow


def base_dir() -> Path:
    """
    Return the base directory for runtime resources.
    - In PyInstaller: sys._MEIPASS (temp extraction dir or app bundle dir)
    - In dev: folder containing this app.py
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def set_windows_app_user_model_id(app_id: str) -> None:
    """
    Helps Windows taskbar treat this executable as its own app,
    improving correct taskbar icon behavior/grouping.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def main():
    # 1) Set AUMID before creating windows (Windows taskbar behavior)
    set_windows_app_user_model_id("MicPlotMaster2.MicPlotMaster")

    app = QApplication(sys.argv)

    # 2) Load runtime icon (prefer PNG; fallback to ICO)
    root = base_dir()
    icon_png = root / "icon.png"
    icon_ico = root / "icon.ico"

    icon_path = icon_png if icon_png.exists() else icon_ico
    app_icon = QIcon(str(icon_path))

    # 3) Apply to application AND main window (covers title bar + taskbar + alt-tab)
    app.setWindowIcon(app_icon)

    win = MainWindow()
    win.setWindowIcon(app_icon)
    win.resize(1200, 700)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()