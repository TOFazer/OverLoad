"""Vue principale de la bibliothèque : grille de vignettes + filtres."""

from __future__ import annotations

from pathlib import Path

try:
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    QWidget = object  # type: ignore

from overload.library.db import LibraryStore
from overload.library.filters import FilterCriteria
from overload.library.models import MEDIA_TYPE_LABELS, MediaEntry, MediaType
from overload.library.scanner import scan_directory

if HAS_QT:

    class ScanWorker(QObject):
        finished = Signal(int)
        progress = Signal(str)

        def __init__(self, store: LibraryStore, folder: Path) -> None:
            super().__init__()
            self.store = store
            self.folder = folder

        def run(self) -> None:
            count = 0
            entries = scan_directory(self.folder, recursive=True, compute_hash=False)
            for e in entries:
                self.store.upsert_entry(e)
                count += 1
                if count % 100 == 0:
                    self.progress.emit(f"{count} fichiers indexés…")
            # Thumbnails en arrière-plan (optionnel)
            try:
                from overload.core.paths import thumbnail_dir
                from overload.library.thumbnails import ensure_thumbnails
                thumbs = thumbnail_dir()
                ensure_thumbnails(entries[:50], thumbs)  # limiter pour ne pas bloquer
            except Exception:
                pass
            self.finished.emit(count)


    class MediaCard(QFrame):
        """Carte vignette pour un fichier."""

        def __init__(self, entry: MediaEntry, parent=None) -> None:
            super().__init__(parent)
            self.entry = entry
            self.setObjectName("card")
            self.setFrameShape(QFrame.StyledPanel)
            self.setFixedSize(220, 200)
            self._build()

        def _build(self) -> None:
            from PySide6.QtWidgets import QVBoxLayout

            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)

            # Vignette
            thumb_label = QLabel()
            thumb_label.setFixedSize(204, 114)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet("background: #0f0f1a; border-radius: 6px;")
            pix = None
            if self.entry.thumbnail_path and Path(self.entry.thumbnail_path).exists():
                pix = QPixmap(str(self.entry.thumbnail_path))
            if pix and not pix.isNull():
                pix = pix.scaled(204, 114, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                thumb_label.setPixmap(pix)
            else:
                icons = {
                    MediaType.VIDEO: "🎬",
                    MediaType.AUDIO: "🎵",
                    MediaType.IMAGE: "🖼️",
                    MediaType.OTHER: "📄",
                }
                icon = icons.get(self.entry.media_type, "📄")
                thumb_label.setText(f"{icon}\n{self.entry.extension.upper().lstrip('.')}")
                thumb_label.setStyleSheet(thumb_label.styleSheet() + " font-size: 14px; font-weight: 600;")
            layout.addWidget(thumb_label)

            # Nom (tronqué)
            name = self.entry.filename
            if len(name) > 28:
                name = name[:25] + "…"
            name_label = QLabel(name)
            name_label.setWordWrap(True)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setStyleSheet("font-weight: 600; font-size: 12px;")
            layout.addWidget(name_label)

            # Métadonnées
            meta = QLabel(
                f"{self.entry.size_human} · {self.entry.mtime_dt.strftime('%d/%m/%Y')}"
                + (f" · {self.entry.duration_human}" if self.entry.duration_human else "")
            )
            meta.setObjectName("muted")
            meta.setAlignment(Qt.AlignCenter)
            meta.setStyleSheet("font-size: 10px;")
            layout.addWidget(meta)

            # Badge type
            badge = QLabel(MEDIA_TYPE_LABELS.get(self.entry.media_type, self.entry.media_type.value))
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: rgba(137,180,250,0.2); border-radius: 4px; padding: 2px 6px; font-size: 10px; color: #89b4fa;"
            )
            layout.addWidget(badge)

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            from overload.ui.widgets.preview_dialog import PreviewDialog
            dlg = PreviewDialog(self.entry, self)
            dlg.exec()


    class LibraryView(QWidget):
        """Grille + filtres + actions."""

        def __init__(self, store: LibraryStore, parent=None) -> None:
            super().__init__(parent)
            self.store = store
            self._entries: list[MediaEntry] = []
            self._build_ui()
            self.refresh()

        def _build_ui(self) -> None:
            from overload.ui.widgets.filter_bar import FilterBar

            outer = QVBoxLayout(self)
            outer.setContentsMargins(12, 12, 12, 12)
            outer.setSpacing(8)

            # En-tête avec stats
            header = QHBoxLayout()
            self.title_label = QLabel("Bibliothèque")
            self.title_label.setObjectName("title")
            self.stats_label = QLabel("")
            self.stats_label.setObjectName("muted")
            header.addWidget(self.title_label)
            header.addWidget(self.stats_label)
            header.addStretch()

            self.add_folder_btn = QPushButton("Ajouter un dossier")
            self.refresh_btn = QPushButton("Actualiser")
            self.refresh_btn.setObjectName("secondary")
            self.duplicates_btn = QPushButton("Voir les doublons")
            self.duplicates_btn.setObjectName("secondary")
            header.addWidget(self.add_folder_btn)
            header.addWidget(self.refresh_btn)
            header.addWidget(self.duplicates_btn)
            outer.addLayout(header)

            # Barre de filtres
            self.filter_bar = FilterBar()
            self.filter_bar.filtersChanged.connect(self.apply_filters)
            outer.addWidget(self.filter_bar)

            # Progression
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            self.progress.setRange(0, 0)
            outer.addWidget(self.progress)

            # Grille
            self.grid = QListWidget()
            self.grid.setViewMode(QListWidget.IconMode)
            self.grid.setResizeMode(QListWidget.Adjust)
            self.grid.setMovement(QListWidget.Static)
            self.grid.setSpacing(8)
            self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
            self.grid.customContextMenuRequested.connect(self._context_menu)
            self.grid.itemDoubleClicked.connect(self._on_double_click)
            outer.addWidget(self.grid, stretch=1)

            # Barre d'état bas
            bottom = QHBoxLayout()
            self.status_label = QLabel("Prêt.")
            self.status_label.setObjectName("muted")
            bottom.addWidget(self.status_label)
            bottom.addStretch()
            outer.addLayout(bottom)

            self.add_folder_btn.clicked.connect(self._add_folder)
            self.refresh_btn.clicked.connect(self.refresh)
            self.duplicates_btn.clicked.connect(self._show_duplicates)

        def refresh(self) -> None:
            entries = self.store.all_entries()
            # Si doublons demandés via filtre, post-filtrer
            self._entries = entries
            self._render(entries)
            self._update_stats()

        def apply_filters(self, criteria: FilterCriteria) -> None:
            params = criteria.normalized()
            only_dup = criteria.only_duplicates
            if only_dup:
                # On récupère tout puis on filtre les doublons
                entries = self.store.search(
                    query=params["query"],
                    media_types=params["media_types"],
                    min_size=params["min_size"],
                    max_size=params["max_size"],
                    after=params["after"],
                    before=params["before"],
                    min_duration=params["min_duration"],
                    max_duration=params["max_duration"],
                    order_by=params["order_by"],
                    descending=params["descending"],
                )
                from overload.library.duplicates import find_duplicates
                groups = find_duplicates(entries, use_partial=True)
                # Aplatir les groupes
                flat = []
                for g in groups:
                    flat.extend(g.entries)
                self._render(flat, empty_msg="Aucun doublon trouvé avec ces filtres.")
            else:
                entries = self.store.search(**{k: v for k, v in params.items() if k != "extension"})
                # Filtre extension supplémentaire si plusieurs
                if criteria.extensions:
                    entries = [e for e in entries if e.extension.lower() in [x.lower() for x in criteria.extensions]]
                self._render(entries)
            self._update_stats(filtered=len(self.grid) if hasattr(self.grid, "__len__") else 0)

        def _render(self, entries: list[MediaEntry], empty_msg: str | None = None) -> None:
            self.grid.clear()
            if not entries:
                item = QListWidgetItem(empty_msg or "Aucun fichier — ajoutez un dossier à indexer.")
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                self.grid.addItem(item)
                self.status_label.setText("Aucun résultat.")
                return

            # Limiter l'affichage pour rester fluide (pagination simple)
            limit = 500
            visible = entries[:limit]
            for entry in visible:
                card = MediaCard(entry)
                item = QListWidgetItem()
                item.setSizeHint(card.sizeHint())
                item.setData(Qt.UserRole, entry)
                self.grid.addItem(item)
                self.grid.setItemWidget(item, card)

            more = len(entries) - limit
            if more > 0:
                self.status_label.setText(f"{len(visible)} affichés sur {len(entries)} — affinez la recherche pour voir le reste.")
            else:
                self.status_label.setText(f"{len(entries)} fichier(s). Double-clic pour prévisualiser.")

        def _update_stats(self, filtered: int | None = None) -> None:
            stats = self.store.stats()
            total = stats["total"]
            by_type = stats["by_type"]
            parts = [f"{total} fichiers"]
            for k in ("video", "audio", "image"):
                if k in by_type:
                    parts.append(f"{by_type[k]['count']} {k}")
            if total == 0:
                self.stats_label.setText("Bibliothèque vide")
            else:
                self.stats_label.setText(" · ".join(parts))

        def _add_folder(self) -> None:
            folder = QFileDialog.getExistingDirectory(self, "Choisir un dossier à indexer")
            if not folder:
                return
            self.progress.setVisible(True)
            self.status_label.setText(f"Indexation de {folder}…")
            # Indexation synchrone pour simplicité (petits dossiers)
            try:
                from overload.library.scanner import index_directory
                count = index_directory(Path(folder), self.store, recursive=True, compute_hash=False)
                QMessageBox.information(self, "Indexation terminée", f"{count} fichiers indexés depuis :\n{folder}")
            except Exception as e:
                QMessageBox.warning(self, "Erreur", str(e))
            finally:
                self.progress.setVisible(False)
            self.refresh()

        def _context_menu(self, pos) -> None:
            item = self.grid.itemAt(pos)
            if not item:
                return
            card = self.grid.itemWidget(item)
            entry: MediaEntry | None = item.data(Qt.UserRole) if item else None
            if not entry and card:
                entry = card.entry
            if not entry:
                return

            menu = QMenu(self)
            open_act = menu.addAction("Ouvrir")
            reveal_act = menu.addAction("Ouvrir l'emplacement")
            menu.addSeparator()
            remove_act = menu.addAction("Retirer de la bibliothèque")
            action = menu.exec(self.grid.mapToGlobal(pos))
            if action == open_act:
                from overload.library.preview import open_media
                try:
                    open_media(entry.path)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", str(e))
            elif action == reveal_act:
                from overload.library.preview import reveal_in_explorer
                try:
                    reveal_in_explorer(entry.path)
                except Exception as e:
                    QMessageBox.warning(self, "Erreur", str(e))
            elif action == remove_act:
                self.store.remove_entry(entry.path)
                self.refresh()

        def _on_double_click(self, item: QListWidgetItem) -> None:
            entry: MediaEntry | None = item.data(Qt.UserRole)
            if not entry:
                w = self.grid.itemWidget(item)
                if w and hasattr(w, "entry"):
                    entry = w.entry
            if entry:
                from overload.ui.widgets.preview_dialog import PreviewDialog
                dlg = PreviewDialog(entry, self)
                dlg.exec()

        def _show_duplicates(self) -> None:
            from overload.library.duplicates import find_duplicates_in_store
            groups = find_duplicates_in_store(self.store, use_partial=True)
            if not groups:
                QMessageBox.information(self, "Doublons", "Aucun doublon détecté.\n\nAstuce : les doublons sont détectés par empreinte du contenu, pas seulement par le nom.")
                return
            # Fenêtre simple listant les groupes
            dlg = DuplicatesDialog(groups, self)
            dlg.exec()


    class DuplicatesDialog(QWidget):
        """Dialog léger pour lister les groupes de doublons."""

        def __init__(self, groups, parent=None) -> None:
            from PySide6.QtWidgets import (
                QDialog,
                QDialogButtonBox,
                QLabel,
                QListWidget,
                QListWidgetItem,
                QVBoxLayout,
            )

            super().__init__(parent)
            # On crée un QDialog wrapper
            self._dlg = QDialog(parent)
            self._dlg.setWindowTitle(f"Doublons — {len(groups)} groupe(s)")
            self._dlg.resize(800, 500)
            layout = QVBoxLayout(self._dlg)
            info = QLabel(
                f"<b>{len(groups)} groupe(s) de doublons</b> — aucun fichier n'a été supprimé.<br>"
                f"<span style='color:#888'>Sélectionnez un fichier pour l'ouvrir ou révéler son emplacement.</span>"
            )
            info.setTextFormat(Qt.RichText)
            layout.addWidget(info)

            for g in groups:
                group_label = QLabel(f"<b>Empreinte {g.hash[:12]}…</b> — {len(g.entries)} fichiers · {g.wasted_human} récupérables si vous supprimez les copies.")
                group_label.setTextFormat(Qt.RichText)
                layout.addWidget(group_label)
                lst = QListWidget()
                for e in g.entries:
                    it = QListWidgetItem(f"{e.filename} — {e.size_human} — {e.path}")
                    it.setData(Qt.UserRole, e)
                    lst.addItem(it)
                lst.itemDoubleClicked.connect(lambda it: self._open_entry(it.data(Qt.UserRole)))
                lst.setContextMenuPolicy(Qt.CustomContextMenu)
                # closure capture
                def make_ctx(lst_widget=lst):
                    def ctx(pos):
                        it = lst_widget.itemAt(pos)
                        if not it:
                            return
                        entry = it.data(Qt.UserRole)
                        m = QMenu(self._dlg)
                        a1 = m.addAction("Ouvrir")
                        a2 = m.addAction("Ouvrir l'emplacement")
                        act = m.exec(lst_widget.mapToGlobal(pos))
                        if act == a1:
                            self._open_entry(entry)
                        elif act == a2:
                            self._reveal_entry(entry)
                    return ctx
                lst.customContextMenuRequested.connect(make_ctx(lst))
                layout.addWidget(lst)

            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.rejected.connect(self._dlg.accept)
            btns.accepted.connect(self._dlg.accept)
            layout.addWidget(btns)
            self._dlg.exec()

        def _open_entry(self, entry) -> None:
            from overload.library.preview import open_media
            try:
                open_media(entry.path)
            except Exception:
                pass

        def _reveal_entry(self, entry) -> None:
            from overload.library.preview import reveal_in_explorer
            try:
                reveal_in_explorer(entry.path)
            except Exception:
                pass

else:
    # Stub pour import sans Qt
    class LibraryView:  # type: ignore
        pass
