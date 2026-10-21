"""Barre de recherche et filtres — toujours visible en haut de la bibliothèque."""

from __future__ import annotations

from datetime import datetime, timedelta

from overload.library.filters import FilterCriteria
from overload.library.models import MediaType

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    HAS_QT = True
except ImportError:
    HAS_QT = False
    QWidget = object  # type: ignore
    Signal = None  # type: ignore


if HAS_QT:

    class FilterBar(QWidget):
        """Barre compacte : recherche, type, taille, date, durée + presets."""

        filtersChanged = Signal(object)  # FilterCriteria

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._build_ui()
            self._connect()

        def _build_ui(self) -> None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 8)
            outer.setSpacing(8)

            # Ligne 1 : recherche + type + bouton effacer
            row1 = QHBoxLayout()
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("Rechercher un fichier (nom, chemin) — ex: vacances été 2024…")
            self.search_input.setClearButtonEnabled(True)

            self.type_combo = QComboBox()
            self.type_combo.addItem("Tous les types", None)
            self.type_combo.addItem("🎬 Vidéos", MediaType.VIDEO)
            self.type_combo.addItem("🎵 Musiques", MediaType.AUDIO)
            self.type_combo.addItem("🖼️ Images", MediaType.IMAGE)
            self.type_combo.addItem("📄 Autres", MediaType.OTHER)

            self.order_combo = QComboBox()
            self.order_combo.addItem("Plus récents", "mtime")
            self.order_combo.addItem("Plus volumineux", "size")
            self.order_combo.addItem("Nom (A→Z)", "filename")
            self.order_combo.addItem("Durée", "duration")

            self.clear_btn = QPushButton("Effacer")
            self.clear_btn.setObjectName("secondary")

            row1.addWidget(self.search_input, stretch=3)
            row1.addWidget(QLabel("Type :"))
            row1.addWidget(self.type_combo)
            row1.addWidget(QLabel("Trier :"))
            row1.addWidget(self.order_combo)
            row1.addWidget(self.clear_btn)
            outer.addLayout(row1)

            # Ligne 2 : taille + date + durée
            row2 = QHBoxLayout()

            self.size_combo = QComboBox()
            self.size_combo.addItem("Toute taille", None)
            self.size_combo.addItem("> 100 Mo", 100 * 1024 * 1024)
            self.size_combo.addItem("> 1 Go", 1024 * 1024 * 1024)
            self.size_combo.addItem("< 10 Mo", -10 * 1024 * 1024)  # négatif = max
            self.size_combo.addItem("< 50 Mo", -50 * 1024 * 1024)

            self.date_combo = QComboBox()
            self.date_combo.addItem("Toute date", None)
            self.date_combo.addItem("Aujourd'hui", "today")
            self.date_combo.addItem("Cette semaine", "week")
            self.date_combo.addItem("Ce mois-ci", "month")
            self.date_combo.addItem("3 derniers mois", "3m")
            self.date_combo.addItem("Cette année", "year")
            self.date_combo.addItem("Il y a plus d'un an", "old")

            self.duration_combo = QComboBox()
            self.duration_combo.addItem("Toute durée", None)
            self.duration_combo.addItem("< 1 min", (None, 60))
            self.duration_combo.addItem("1–5 min", (60, 300))
            self.duration_combo.addItem("5–30 min", (300, 1800))
            self.duration_combo.addItem("> 30 min", (1800, None))

            # Presets rapides
            self.preset_duplicates = QPushButton("Doublons")
            self.preset_duplicates.setObjectName("secondary")
            self.preset_duplicates.setCheckable(True)

            row2.addWidget(QLabel("Taille :"))
            row2.addWidget(self.size_combo)
            row2.addWidget(QLabel("Date :"))
            row2.addWidget(self.date_combo)
            row2.addWidget(QLabel("Durée :"))
            row2.addWidget(self.duration_combo)
            row2.addWidget(self.preset_duplicates)
            row2.addStretch()
            outer.addLayout(row2)

        def _connect(self) -> None:
            self.search_input.textChanged.connect(self._emit)
            self.search_input.returnPressed.connect(self._emit)
            self.type_combo.currentIndexChanged.connect(self._emit)
            self.order_combo.currentIndexChanged.connect(self._emit)
            self.size_combo.currentIndexChanged.connect(self._emit)
            self.date_combo.currentIndexChanged.connect(self._emit)
            self.duration_combo.currentIndexChanged.connect(self._emit)
            self.preset_duplicates.toggled.connect(self._emit)
            self.clear_btn.clicked.connect(self.reset)

        def reset(self) -> None:
            self.search_input.clear()
            self.type_combo.setCurrentIndex(0)
            self.order_combo.setCurrentIndex(0)
            self.size_combo.setCurrentIndex(0)
            self.date_combo.setCurrentIndex(0)
            self.duration_combo.setCurrentIndex(0)
            self.preset_duplicates.setChecked(False)
            self._emit()

        def criteria(self) -> FilterCriteria:
            q = self.search_input.text().strip() or None
            media_types = None
            mt = self.type_combo.currentData()
            if mt is not None:
                media_types = [mt]

            min_size = max_size = None
            sz = self.size_combo.currentData()
            if sz is not None:
                if sz > 0:
                    min_size = sz
                else:
                    max_size = -sz

            after = before = None
            now = datetime.now()
            date_key = self.date_combo.currentData()
            if date_key == "today":
                after = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif date_key == "week":
                after = now - timedelta(days=7)
            elif date_key == "month":
                after = now - timedelta(days=30)
            elif date_key == "3m":
                after = now - timedelta(days=90)
            elif date_key == "year":
                after = now - timedelta(days=365)
            elif date_key == "old":
                before = now - timedelta(days=365)

            min_duration = max_duration = None
            dur = self.duration_combo.currentData()
            if dur is not None:
                min_duration, max_duration = dur

            order_by = self.order_combo.currentData() or "mtime"
            descending = order_by in ("mtime", "size", "duration")

            return FilterCriteria(
                query=q,
                media_types=media_types,
                min_size=min_size,
                max_size=max_size,
                after=after,
                before=before,
                min_duration=min_duration,
                max_duration=max_duration,
                only_duplicates=self.preset_duplicates.isChecked(),
                order_by=order_by,
                descending=descending,
            )

        def _emit(self) -> None:
            self.filtersChanged.emit(self.criteria())

else:
    # Fallback sans Qt — utilisé dans les tests
    class FilterBar:  # type: ignore
        pass
