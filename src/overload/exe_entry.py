"""Point d'entrée GUI natif embarqué dans `OverLoad.exe` (sans console Windows)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _ensure_standard_streams() -> None:
    """Évite tout crash sous Windows en mode `--windowed` où stdout/stderr valent `None`."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def main(argv: list[str] | None = None) -> int:
    _ensure_standard_streams()
    args = list(sys.argv[1:] if argv is None else argv)

    if "--self-test" in args:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        out_file: Path | None = None
        if "--self-test-out" in args:
            idx = args.index("--self-test-out")
            if idx + 1 < len(args):
                out_file = Path(args[idx + 1])

        from overload.ui.desktop import launch_desktop_app

        with tempfile.TemporaryDirectory(prefix="overload-selftest-") as tmp:
            tmp_dir = Path(tmp)
            if getattr(sys, "frozen", False):
                import wave

                import yt_dlp

                from overload.media.analyzer import analyze

                sample = tmp_dir / "test audio.wav"
                with wave.open(str(sample), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(b"\x00\x00" * 8000)
                report = analyze(sample)
                if "sans erreur" not in report.integrity:
                    raise RuntimeError("Auto-test FFmpeg : " + report.explanation())
                if not yt_dlp.version.__version__:
                    raise RuntimeError("Auto-test YouTube : yt-dlp est inutilisable.")
            code = launch_desktop_app(
                destination_dir=tmp_dir / "Downloads",
                data_dir=tmp_dir / "Data",
                self_test=True,
            )
        if out_file is not None:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(
                json.dumps({"status": "ok", "exit_code": code}),
                encoding="utf-8",
            )
        return code

    # Délègue toute sous-commande CLI explicite (`download`, `batch`, `serve`) à `__main__`
    if args and args[0] in {"download", "batch", "serve", "-h", "--help"}:
        from overload.__main__ import main as cli_main

        return cli_main(args)

    from overload.ui.desktop import launch_desktop_app

    return launch_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())
