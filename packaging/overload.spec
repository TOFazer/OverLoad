# -*- mode: python ; coding: utf-8 -*-
"""Spécification PyInstaller : OverLoad.exe portable, fenêtre sans console.
Construction (Windows) :  pyinstaller packaging/overload.spec --noconfirm
Résultat :                dist/OverLoad.exe
Le fichier est autonome : Python, PySide6 et les ressources sont embarqués.
Aucun outil n'est requis sur le poste de l'utilisateur.
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - fourni par PyInstaller
# Modules Qt inutilisés : retirés pour réduire la taille et la surface d'attaque.
EXCLUDED_QT = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "tkinter",
]
a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OverLoad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX peut déclencher de faux positifs antivirus
    console=False,  # pas de fenêtre console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "overload.ico"),
    version=None,
)
