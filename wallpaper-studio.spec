# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Wallpaper Studio.

Build with:  pyinstaller wallpaper-studio.spec

Produces a single self-contained executable in dist/. The Python interpreter,
the standard library and the web page are all inside it, so the machine running
it needs nothing installed.
"""

import os
import sys

# Files the app reads at runtime. wallpaper-studio.html is the app itself; the
# scripts are here so the page's "Download helper script" buttons still work in
# a packaged build. resource() in wallpaper_server.py looks beside the
# executable first, so a user can drop in an edited page without a rebuild.
datas = [
    ("wallpaper-studio.html", "."),
    ("wallpaper_server.py", "."),
    ("start.bat", "."),
    ("start.command", "."),
]
datas = [(src, dst) for src, dst in datas if os.path.exists(src)]

a = Analysis(
    ["wallpaper_server.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    # tkinter is imported lazily inside the folder-picker, and winreg only on
    # Windows; name them so the analysis can't miss them.
    hiddenimports=["tkinter", "tkinter.filedialog"],
    hookspath=[],
    runtime_hooks=[],
    # Nothing here uses these, and they add tens of megabytes.
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PIL",
        "pytest", "setuptools", "pip", "unittest", "pydoc_data",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Finder runs an extension-less Unix executable in Terminal on double-click, so
# the friendly name works on macOS. Windows needs the .exe, which PyInstaller
# appends automatically.
name = "WallpaperStudio" if sys.platform == "win32" else "Wallpaper Studio"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # Keep the console: it carries the startup banner, the folder paths and the
    # log, and closing that window is how you stop the server.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
