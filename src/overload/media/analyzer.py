"""Analyse locale, sans modification des médias ni accès réseau des outils FFmpeg."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Report:
    path: Path
    metadata: dict = field(default_factory=dict)
    integrity: str = "Non vérifiée"
    issues: list[str] = field(default_factory=list)

    def explanation(self) -> str:
        intro = f"Vérification de lecture : {self.integrity}."
        notes = self.issues or [
            "Aucun obstacle courant détecté. Cela ne garantit pas l'importation : "
            "le logiciel de montage, sa version et le matériel restent déterminants."
        ]
        return intro + "\n\n" + "\n\n".join(notes)


def tool_path(name: str) -> str:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    bundled = root / "tools" / f"{name}.exe"
    if bundled.is_file():
        return str(bundled)
    installed = shutil.which(name)
    if installed:
        return installed
    raise RuntimeError(
        f"{name} est introuvable. Utilisez l'édition Windows complète ou installez FFmpeg "
        "avec ffprobe dans le PATH pour le développement."
    )


def _run(name: str, args: list[str], timeout: int) -> tuple[int, str, str]:
    # Les journaux d'un fichier abîmé peuvent être volumineux : pas de PIPE en mémoire.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        result = subprocess.run(
            [tool_path(name), *args],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out.seek(0)
        err.seek(0)
        return (
            result.returncode,
            out.read(8_000_000).decode("utf-8", "replace"),
            err.read(4000).decode("utf-8", "replace"),
        )


def run_tool(name: str, args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Exécute un outil FFmpeg/FFprobe embarqué (usage public : espace Créateurs)."""
    return _run(name, args, timeout)


def number(value: object) -> float | None:
    try:
        result = float(str(value))
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError):
        return None


def fps(value: object) -> float | None:
    try:
        a, b = str(value).split("/")
        return number(float(a) / float(b))
    except (ValueError, ZeroDivisionError):
        return number(value)


def compatibility(metadata: dict) -> list[str]:
    issues = []
    streams = metadata.get("streams", [])
    if not any(s.get("codec_type") in {"video", "audio"} for s in streams):
        issues.append(
            "Aucune piste vidéo ou audio reconnue : ce fichier n'est peut-être pas un média."
        )
    for stream in streams:
        kind, codec = stream.get("codec_type"), stream.get("codec_name", "inconnu")
        label = f"Piste {stream.get('index', '?')} ({codec})"
        if kind == "video":
            if codec not in {"h264", "mpeg2video", "prores", "dnxhd", "mjpeg", "dvvideo"}:
                issues.append(
                    f"{label} : ce codec peut manquer dans votre logiciel, notamment HEVC/AV1. "
                    "Vérifiez sa prise en charge ou convertissez une copie en ProRes/DNxHR."
                )
            pix = stream.get("pix_fmt", "")
            if pix and pix not in {"yuv420p", "yuvj420p"}:
                issues.append(
                    f"{label} : le format de couleur {pix} peut nécessiter un décodeur adapté "
                    "(10 bits, 4:2:2…). Essayez des proxies ou un codec intermédiaire."
                )
            avg, nominal = fps(stream.get("avg_frame_rate")), fps(stream.get("r_frame_rate"))
            if avg and nominal and abs(avg - nominal) / nominal > 0.01:
                issues.append(
                    f"{label} : les cadences déclarées diffèrent. "
                    "Une cadence variable est possible "
                    "(non prouvée) et peut désynchroniser le son. "
                    "Une copie à FPS constants peut aider."
                )
        elif kind == "audio" and codec not in {"aac", "mp3", "pcm_s16le", "pcm_s24le"}:
            issues.append(
                f"{label} : le son peut être refusé par certains monteurs. "
                "Convertissez une copie de la piste en PCM ou AAC."
            )
        elif kind == "subtitle":
            issues.append(
                f"{label} : les sous-titres intégrés ne sont pas toujours importés. "
                "Exportez-les séparément dans un format accepté par le monteur."
            )
    containers = metadata.get("format", {}).get("format_name", "").split(",")
    if any(c in containers for c in ("matroska", "webm", "mpegts", "ogg")):
        issues.append(
            "Le conteneur peut être refusé même si les codecs sont lisibles. "
            "Un remuxage vers MP4/MOV peut suffire si les pistes sont compatibles ; "
            "changer seulement l'extension ne convertit pas le fichier."
        )
    return issues


def analyze(path: Path, *, deep: bool = True, timeout: int = 600) -> Report:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError("Sélectionnez un fichier local existant.")
    report = Report(path)
    if path.stat().st_size == 0:
        report.integrity = "Fichier vide"
        report.issues.append(
            "Il ne contient aucune donnée. Téléchargez ou copiez le fichier à nouveau."
        )
        return report
    try:
        code, raw, errors = _run(
            "ffprobe",
            [
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            60,
        )
    except subprocess.TimeoutExpired:
        report.integrity = "Indéterminée (délai d'analyse dépassé)"
        report.issues.append(
            "L'analyse a pris trop de temps. Le fichier n'est pas forcément endommagé."
        )
        return report
    if code:
        report.integrity = "Illisible ou incomplet possible"
        report.issues.append(
            "L'outil ne peut pas lire la structure du fichier. Il peut être incomplet, endommagé "
            "ou dans un format non pris en charge. Reprenez le transfert depuis l'original."
        )
        report.issues.append("Détail technique : " + errors.strip())
        return report
    try:
        report.metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Réponse FFprobe invalide ou trop volumineuse.") from exc
    report.issues.extend(compatibility(report.metadata))
    if errors.strip():
        report.issues.append("La structure présente des anomalies : " + errors.strip())
    if path.suffix.lower() in {".part", ".tmp", ".crdownload"}:
        report.issues.append("Cette extension indique un transfert temporaire : attendez sa fin.")
    if deep:
        try:
            code, _, errors = _run(
                "ffmpeg",
                [
                    "-hide_banner",
                    "-v",
                    "error",
                    "-nostdin",
                    "-xerror",
                    "-protocol_whitelist",
                    "file",
                    "-i",
                    str(path),
                    "-map",
                    "0:v?",
                    "-map",
                    "0:a?",
                    "-sn",
                    "-dn",
                    "-f",
                    "null",
                    "-",
                ],
                timeout,
            )
            report.integrity = (
                "Erreurs de lecture détectées"
                if code or errors.strip()
                else ("Lecture complète audio/vidéo sans erreur détectée")
            )
            if code or errors.strip():
                report.issues.append(
                    "Certains passages ne peuvent pas être décodés. Une copie peut être abîmée, "
                    "incomplète ou utiliser un codec indisponible. Réessayez avec l'original.\n"
                    + errors.strip()
                )
        except subprocess.TimeoutExpired:
            report.integrity = "Indéterminée : vérification arrêtée après le délai maximal"
            report.issues.append(
                "Le fichier est long ou lent à décoder. Ce délai ne prouve pas une panne."
            )
    report.issues.append(
        "Même une lecture sans erreur ne prouve pas que la fin attendue est présente : "
        "comparez la durée ou l'empreinte avec l'original si le transfert semble incomplet."
    )
    return report
