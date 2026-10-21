"""Prépare les outils LGPL Windows depuis BtbN (aucun binaire conservé dans Git)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare() -> None:
    target = ROOT / "tools"
    target.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        subprocess.run(
            [
                "gh",
                "release",
                "download",
                "latest",
                "--repo",
                "BtbN/FFmpeg-Builds",
                "--pattern",
                "ffmpeg-master-latest-win64-lgpl.zip",
                "--dir",
                str(folder),
            ],
            check=True,
        )
        archive = folder / "ffmpeg-master-latest-win64-lgpl.zip"
        with zipfile.ZipFile(archive) as zf:
            # N'extraire que les noms relatifs sûrs de cette archive tierce.
            for member in zf.infolist():
                parts = Path(member.filename).parts
                if Path(member.filename).is_absolute() or ".." in parts:
                    raise ValueError("Chemin non sûr dans l'archive FFmpeg")
            zf.extractall(folder / "extracted")
        extracted = folder / "extracted"
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            source = next(extracted.rglob(name))
            shutil.copy2(source, target / name)
        # Notices, licence LGPL et documentation/source proposées par le distributeur.
        for item in extracted.iterdir():
            for child in item.iterdir():
                if child.name != "bin":
                    dest = target / child.name
                    if child.is_dir():
                        shutil.copytree(child, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(child, dest)
    print("Outils FFmpeg LGPL prêts dans tools/.")


if __name__ == "__main__":
    prepare()
