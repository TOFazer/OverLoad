"""Script officiel de construction de l'exécutable Windows `OverLoad.exe`.

Produit dans `dist/` :
1. `dist/OverLoad.exe` — exécutable autonome tout-en-un prêt à lancer sans installation.
2. `dist/OverLoad-Portable-win64.zip` — édition portable rapide avec dossier `OverLoad-data`
   et bibliothèques dynamiques Qt remplaçables (conformité LGPL v3).
3. `dist/SHA256SUMS.txt` — sommes de contrôle SHA-256 des livrables.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

HIDDEN_IMPORTS = [
    "overload",
    "overload.core.errors",
    "overload.core.formatting",
    "overload.core.paths",
    "overload.creators",
    "overload.creators.fsutil",
    "overload.creators.models",
    "overload.creators.profiles",
    "overload.creators.renaming",
    "overload.creators.scan",
    "overload.creators.store",
    "overload.creators.structure",
    "overload.creators.subtitles",
    "overload.creators.workspace",
    "overload.downloads",
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
    "overload.downloads.youtube",
    "overload.history.store",
    "overload.library",
    "overload.library.scan",
    "overload.media.analyzer",
    "overload.settings.store",
    "overload.ui.analyzer",
    "overload.ui.components",
    "overload.ui.creators",
    "overload.ui.desktop",
    "overload.ui.failure_text",
    "overload.ui.icons",
    "overload.ui.theme",
    "overload.ui.web.server",
    "overload.ui.window",
    "yt_dlp",
]

EXCLUDES = [
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
]


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _common_pyinstaller_args(icon_path: Path) -> list[str]:
    sep = ";" if sys.platform == "win32" else ":"
    static_src = ROOT / "src" / "overload" / "ui" / "web" / "static"
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        if not (ROOT / "tools" / name).is_file():
            raise RuntimeError("Exécutez python scripts/prepare_ffmpeg.py avant la compilation.")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--paths",
        str(ROOT / "src"),
        "--icon",
        str(icon_path),
        "--add-data",
        f"{static_src}{sep}overload/ui/web/static",
        "--add-data",
        f"{ROOT / 'tools'}{sep}tools",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", mod])
    # yt-dlp charge ses extracteurs dynamiquement : PyInstaller doit les embarquer.
    cmd.extend(["--collect-submodules", "yt_dlp"])
    for exc in EXCLUDES:
        cmd.extend(["--exclude-module", exc])
    return cmd


def ensure_media_tools() -> None:
    """Prépare les outils aussi pour les builds lancés sans l'étape CI dédiée."""
    required = (ROOT / "tools" / name for name in ("ffmpeg.exe", "ffprobe.exe"))
    if all(path.is_file() for path in required):
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    from prepare_ffmpeg import prepare

    prepare()
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        if not (ROOT / "tools" / name).is_file():
            raise RuntimeError(f"Préparation incomplète : {name} est absent.")


def build_all() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_icon import generate_ico

    # Vérifier les dépendances avant de supprimer les livrables existants.
    ensure_media_tools()
    icon = generate_ico()
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.rmtree(BUILD, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)

    entry = str(ROOT / "src" / "overload" / "exe_entry.py")

    print("1/3 Compilation de l'édition portable (dossier OverLoad/)...", flush=True)
    subprocess.run(
        [
            *_common_pyinstaller_args(icon),
            "--onedir",
            "--name",
            "OverLoad-Portable",
            "--distpath",
            str(DIST / "_portable_stage"),
            entry,
        ],
        check=True,
    )

    stage_dir = DIST / "_portable_stage" / "OverLoad-Portable"
    exe_name = "OverLoad-Portable.exe" if sys.platform == "win32" else "OverLoad-Portable"
    exe_in_dir = stage_dir / exe_name
    renamed_exe = stage_dir / ("OverLoad.exe" if sys.platform == "win32" else "OverLoad")
    exe_in_dir.rename(renamed_exe)
    (stage_dir / "OverLoad-data").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", stage_dir / "LICENSE.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_LICENSES.md", stage_dir / "THIRD_PARTY_LICENSES.md")

    portable_zip = DIST / "OverLoad-Portable-win64.zip"
    with zipfile.ZipFile(portable_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(stage_dir.rglob("*")):
            arcname = Path("OverLoad") / item.relative_to(stage_dir)
            zf.write(item, str(arcname))
    shutil.rmtree(DIST / "_portable_stage", ignore_errors=True)

    print("2/3 Compilation de l'exécutable autonome unique (dist/OverLoad.exe)...", flush=True)
    subprocess.run(
        [
            *_common_pyinstaller_args(icon),
            "--onefile",
            "--name",
            "OverLoad",
            "--distpath",
            str(DIST),
            entry,
        ],
        check=True,
    )

    single_exe = DIST / ("OverLoad.exe" if sys.platform == "win32" else "OverLoad")
    shutil.copy2(ROOT / "LICENSE", DIST / "LICENSE.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_LICENSES.md", DIST / "THIRD_PARTY_LICENSES.md")

    print("3/3 Calcul des empreintes SHA-256...", flush=True)
    sums_lines = [
        f"{_sha256(single_exe)}  {single_exe.name}",
        f"{_sha256(portable_zip)}  {portable_zip.name}",
    ]
    sums_file = DIST / "SHA256SUMS.txt"
    sums_file.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    for line in sums_lines:
        print(" ", line, flush=True)


if __name__ == "__main__":
    build_all()
