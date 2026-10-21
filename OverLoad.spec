# -*- mode: python ; coding: utf-8 -*-
"""Spécification PyInstaller directe : `pyinstaller OverLoad.spec` -> `dist/OverLoad.exe`."""

from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "src" / "overload" / "exe_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "overload" / "ui" / "web" / "static"), "overload/ui/web/static"),
        (str(ROOT / "tools"), "tools"),
    ],
    hiddenimports=[
        "overload.core.errors",
        "overload.core.formatting",
        "overload.core.paths",
        "overload.downloads.bandwidth",
        "overload.downloads.duplicates",
        "overload.downloads.engine",
        "overload.downloads.files",
        "overload.downloads.manager",
        "overload.downloads.models",
        "overload.downloads.netguard",
        "overload.downloads.state",
        "overload.downloads.telemetry",
        "overload.downloads.urls",
        "overload.history.store",
        "overload.settings.store",
        "overload.ui.desktop",
        "overload.ui.theme",
        "overload.ui.web.server",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "_pytest",
        "ruff",
        "tkinter",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OverLoad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=str(ROOT / "assets" / "overload.ico"),
)
