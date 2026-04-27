# resources.py

import sys
from pathlib import Path

def resource_path(relative_path: str) -> Path:
    """
    Resolve resource paths for:
    - development
    - PyInstaller onedir
    - PyInstaller onefile
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(relative_path)