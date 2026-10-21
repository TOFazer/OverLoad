# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec pour OverLoad.exe (Windows 11)

Usage :
  pip install -e ".[build]"
  pyinstaller overload.spec
  # -> dist/OverLoad.exe
  # Installateur : voir installer/OverLoad.iss (Inno Setup)

Notes :
- PySide6 est ~120 Mo empaqueté ; on exclut les tests et docs.
- L'app reste portable si un dossier OverLoad-data existe à côté de l'exe.
"""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ["src/overload/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Si des icônes/resources étaient ajoutés, les lister ici.
        # ("src/overload/ui/resources", "overload/ui/resources"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "tests"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="OverLoad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # fenêtre GUI sans console (mettre True pour debug)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="src/overload/ui/resources/icon.ico" if False else None,
)
