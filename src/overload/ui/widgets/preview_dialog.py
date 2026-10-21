"""Dialogue de prévisualisation d'un média."""

from __future__ import annotations

from pathlib import Path

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    QDialog = object  # type: ignore

if HAS_QT:

    class PreviewDialog(QDialog):
        def __init__(self, entry, parent=None) -> None:
            super().__init__(parent)
            self.entry = entry
            self.setWindowTitle(f"Aperçu — {entry.filename}")
            self.resize(720, 560)
            self._build()

        def _build(self) -> None:
            layout = QVBoxLayout(self)

            # Zone image / vignette
            self.preview_label = QLabel()
            self.preview_label.setAlignment(Qt.AlignCenter)
            self.preview_label.setStyleSheet("background: #111; border-radius: 8px; padding: 8px;")
            self.preview_label.setMinimumHeight(320)

            thumb = None
            if self.entry.thumbnail_path and Path(self.entry.thumbnail_path).exists():
                thumb = str(self.entry.thumbnail_path)
                pix = QPixmap(thumb)
                if not pix.isNull():
                    pix = pix.scaled(640, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.preview_label.setPixmap(pix)
                    thumb = None  # déjà affiché
            if thumb is not False and self.preview_label.pixmap() is None:
                # Placeholder texte
                if self.entry.media_type.value == "video":
                    self.preview_label.setText("🎬\nAperçu vidéo\n(lecture dans le lecteur par défaut)")
                elif self.entry.media_type.value == "audio":
                    self.preview_label.setText("🎵\nAperçu audio\n(lecture dans le lecteur par défaut)")
                elif self.entry.media_type.value == "image":
                    # Essayer d'afficher l'image source directement
                    pix = QPixmap(str(self.entry.path))
                    if not pix.isNull():
                        pix = pix.scaled(640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.preview_label.setPixmap(pix)
                    else:
                        self.preview_label.setText(f"🖼️\n{self.entry.filename}")
                else:
                    self.preview_label.setText(f"📄\n{self.entry.filename}")

            layout.addWidget(self.preview_label)

            # Infos
            info = QLabel(
                f"<b>{self.entry.filename}</b><br>"
                f"<span style='color:#888'>{self.entry.media_type.value} · {self.entry.size_human} · "
                f"{self.entry.mtime_dt.strftime('%d/%m/%Y %H:%M')} "
                f"{'· ' + self.entry.duration_human if self.entry.duration_human else ''}</span><br>"
                f"<span style='font-size:11px; color:#aaa'>{self.entry.path}</span>"
            )
            info.setWordWrap(True)
            info.setTextFormat(Qt.RichText)
            layout.addWidget(info)

            # Boutons
            btns = QHBoxLayout()
            open_btn = QPushButton("Ouvrir")
            reveal_btn = QPushButton("Ouvrir l'emplacement")
            reveal_btn.setObjectName("secondary")
            close_btn = QPushButton("Fermer")
            close_btn.setObjectName("secondary")

            open_btn.clicked.connect(self._open)
            reveal_btn.clicked.connect(self._reveal)
            close_btn.clicked.connect(self.accept)

            btns.addWidget(open_btn)
            btns.addWidget(reveal_btn)
            btns.addStretch()
            btns.addWidget(close_btn)
            layout.addLayout(btns)

        def _open(self) -> None:
            from overload.library.preview import open_media
            try:
                open_media(self.entry.path)
            except Exception as e:
                self.preview_label.setText(f"Erreur : {e}")

        def _reveal(self) -> None:
            from overload.library.preview import reveal_in_explorer
            try:
                reveal_in_explorer(self.entry.path)
            except Exception as e:
                self.preview_label.setText(f"Erreur : {e}")

