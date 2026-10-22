"""Onglet Qt : travaux coûteux hors du thread graphique, résultats via une file."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from overload.media.analyzer import Report, analyze, fps, number
from overload.ui.filedialogs import choose_open_file


def create_analyzer_widget():
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    hint = QLabel(
        "À quoi ça sert : vérifier un fichier AVANT de l'importer dans un logiciel de "
        "montage (Premiere Pro, DaVinci Resolve, CapCut…). OverLoad affiche le conteneur, "
        "les codecs, la résolution, la cadence, la durée et toutes les pistes, puis signale "
        "les risques connus (codec rare, cadence variable, couleurs 10 bits…). Fichiers "
        "acceptés : vidéos et audios locaux. L'analyse est 100 % locale, ne modifie jamais "
        "le fichier et ne convertit rien en silence ; la lecture complète peut durer "
        "jusqu'à 10 minutes. Les alertes sont indicatives, pas une certification."
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    row = QHBoxLayout()
    path = QLineEdit()
    path.setPlaceholderText("Choisissez un fichier vidéo ou audio…")
    path.setObjectName("analyzerPath")
    browse = QPushButton("Parcourir…")
    start = QPushButton("Analyser")
    start.setObjectName("analyzerStart")
    row.addWidget(path, 1)
    row.addWidget(browse)
    row.addWidget(start)
    layout.addLayout(row)
    deep = QCheckBox("Vérifier la lecture complète audio/vidéo (plus lent)")
    deep.setChecked(True)
    layout.addWidget(deep)
    status = QLabel("Prêt à analyser un fichier.")
    status.setObjectName("analyzerStatus")
    status.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(status)
    output = QPlainTextEdit()
    output.setReadOnly(True)
    output.setObjectName("analyzerOutput")
    layout.addWidget(output)
    why = QPushButton("Pourquoi ce fichier ne fonctionne-t-il pas ?")
    why.setEnabled(False)
    layout.addWidget(why)
    results: queue.Queue = queue.Queue()
    report: Report | None = None

    def choose():
        # Démarre sur le fichier déjà indiqué (ou son dossier), jamais « n'importe où ».
        filename = choose_open_file(
            widget, "Choisir un média", preferred=path.text().strip() or None
        )
        if filename:
            path.setText(filename)

    def work(filename, full):
        try:
            results.put(analyze(Path(filename), deep=full))
        except Exception as exc:
            results.put(str(exc))

    def launch():
        nonlocal report
        if not path.text().strip():
            status.setText("Choisissez d'abord un fichier.")
            return
        report = None
        why.setEnabled(False)
        for control in (start, browse, path, deep):
            control.setEnabled(False)
        output.clear()
        status.setText("Analyse en cours… L'interface reste disponible.")
        threading.Thread(target=work, args=(path.text(), deep.isChecked()), daemon=True).start()
        timer.start()

    def collect():
        nonlocal report
        try:
            result = results.get_nowait()
        except queue.Empty:
            return
        timer.stop()
        for control in (start, browse, path, deep):
            control.setEnabled(True)
        if not isinstance(result, Report):
            status.setText("Analyse impossible : " + result)
            return
        report = result
        status.setText(result.integrity)
        fmt = result.metadata.get("format", {})
        lines = [
            str(result.path),
            f"Conteneur : {fmt.get('format_long_name', 'Inconnu')}",
            f"Durée : {fmt.get('duration', 'Inconnue')} s",
            f"Débit global : {_bitrate(fmt.get('bit_rate'))}",
            "",
            "PISTES DISPONIBLES",
        ]
        for stream in result.metadata.get("streams", []):
            tags = stream.get("tags", {})
            disposition = stream.get("disposition", {})
            lines.append(
                f"\n#{stream.get('index', '?')} — {stream.get('codec_type', '?')} — "
                f"{stream.get('codec_long_name', stream.get('codec_name', 'Inconnu'))}"
            )
            lines.append(
                f"Langue : {tags.get('language', 'non précisée')} | "
                f"Titre : {tags.get('title', '—')} | "
                f"Par défaut : {'oui' if disposition.get('default') else 'non'} | "
                f"Forcée : {'oui' if disposition.get('forced') else 'non'}"
            )
            if stream.get("codec_type") == "video":
                cadence = fps(stream.get("avg_frame_rate"))
                lines.append(
                    f"Résolution : {stream.get('width', '?')} × {stream.get('height', '?')} | "
                    f"FPS moyens : {f'{cadence:.3f}' if cadence else 'inconnus'} | "
                    f"Couleur : {stream.get('pix_fmt', '?')}"
                )
            if stream.get("codec_type") == "audio":
                lines.append(
                    f"Canaux : {stream.get('channels', '?')} "
                    f"({stream.get('channel_layout', '?')}) | "
                    f"Échantillonnage : {stream.get('sample_rate', '?')} Hz"
                )
            lines.append(f"Débit piste : {_bitrate(stream.get('bit_rate'))}")
        output.setPlainText("\n".join(lines) + "\n\nDIAGNOSTIC\n" + result.explanation())
        why.setEnabled(True)

    def explain():
        if report:
            dialog = QMessageBox(widget)
            dialog.setWindowTitle("Comprendre le problème")
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(report.explanation())
            dialog.exec()

    timer = QTimer(widget)
    timer.setInterval(100)
    def set_file(filename: str) -> None:
        """Préremplit le champ fichier (ex. depuis la bibliothèque)."""
        path.setText(str(filename))
        status.setText("Fichier prêt à analyser : cliquez sur « Analyser ».")

    widget.set_file = set_file  # type: ignore[attr-defined]
    timer.timeout.connect(collect)
    browse.clicked.connect(choose)
    start.clicked.connect(launch)
    why.clicked.connect(explain)
    return widget


def _bitrate(value):
    rate = number(value)
    return f"{rate / 1000:,.0f} kbit/s" if rate else "Non renseigné"
