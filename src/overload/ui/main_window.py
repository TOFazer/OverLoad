"""Fenêtre principale OverLoad — navigation entre sections."""

from __future__ import annotations

from pathlib import Path

try:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    QMainWindow = object  # type: ignore

if HAS_QT:
    from overload.core.paths import app_data_dir, library_db_path
    from overload.library.db import LibraryStore
    from overload.library.organizer import OrganizerConfig
    from overload.settings.store import SettingsStore

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("OverLoad — Votre média, à votre façon")
            self.resize(1200, 750)
            self.settings = SettingsStore()
            db_path = library_db_path()
            self.store = LibraryStore(db_path)
            self._build_ui()

        def _build_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)
            outer = QHBoxLayout(central)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            # Sidebar
            sidebar = QWidget()
            sidebar.setFixedWidth(210)
            sidebar.setStyleSheet("background: #11111b;" if self.settings.get("theme") != "light" else "background: #dce0e8;")
            side_layout = QVBoxLayout(sidebar)
            side_layout.setContentsMargins(8, 12, 8, 12)
            side_layout.setSpacing(4)

            title = QLabel("⚡ OverLoad")
            title.setStyleSheet("font-size: 18px; font-weight: 800; padding: 8px;")
            side_layout.addWidget(title)

            subtitle = QLabel("Organise et prépare tes médias")
            subtitle.setObjectName("muted")
            subtitle.setStyleSheet("font-size: 11px; padding: 0 8px 12px 8px;")
            side_layout.addWidget(subtitle)

            self.nav = QListWidget()
            self.nav.setStyleSheet(
                "QListWidget { background: transparent; border: none; }"
                "QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 2px 0; }"
                "QListWidget::item:selected { background: #89b4fa; color: #1e1e2e; }"
                "QListWidget::item:hover { background: rgba(137,180,250,0.15); }"
            )
            for label in ["📚 Bibliothèque", "⬇️ Téléchargements", "⭐ Classement auto", "⚙️ Paramètres", "ℹ️ À propos"]:
                it = QListWidgetItem(label)
                self.nav.addItem(it)
            self.nav.setCurrentRow(0)
            self.nav.currentRowChanged.connect(self._switch_page)
            side_layout.addWidget(self.nav)

            side_layout.addStretch()
            version = QLabel("v0.1.0 • Windows 11")
            version.setObjectName("muted")
            version.setStyleSheet("font-size: 10px; padding: 8px;")
            side_layout.addWidget(version)

            outer.addWidget(sidebar)

            # Contenu
            self.stack = QStackedWidget()
            outer.addWidget(self.stack, stretch=1)

            # Pages
            self._build_library_page()
            self._build_downloads_page()
            self._build_organizer_page()
            self._build_settings_page()
            self._build_about_page()

        def _build_library_page(self) -> None:
            from overload.ui.library_view import LibraryView
            page = LibraryView(self.store)
            self.stack.addWidget(page)
            self.library_page = page

        def _build_downloads_page(self) -> None:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(QLabel("<h2>⬇️ Téléchargements</h2>"))
            layout.addWidget(QLabel("Collez une adresse directe (https://…) — OverLoad ne contourne aucune protection."))
            # Champ URL
            form = QHBoxLayout()
            self.url_input = QLineEdit()
            self.url_input.setPlaceholderText("https://example.com/fichier.mp4")
            self.download_btn = QPushButton("Télécharger")
            form.addWidget(self.url_input, stretch=1)
            form.addWidget(self.download_btn)
            layout.addLayout(form)

            hint = QLabel("Le fichier sera classé automatiquement selon vos règles (page Classement auto).")
            hint.setObjectName("muted")
            layout.addWidget(hint)

            # Liste des tâches (placeholder, branché sur downloads/engine)
            self.download_status = QLabel("Aucun téléchargement en cours.")
            self.download_status.setObjectName("muted")
            layout.addWidget(self.download_status)
            layout.addStretch()

            def do_download():
                url = self.url_input.text().strip()
                if not url:
                    QMessageBox.warning(self, "Adresse manquante", "Collez une adresse de fichier (https://…).")
                    return
                dest_dir = self.settings.download_dir()
                if not dest_dir:
                    dest_dir = Path.home() / "Downloads" / "OverLoad"
                dest_dir.mkdir(parents=True, exist_ok=True)
                from overload.core.errors import OverloadError
                from overload.downloads.engine import download_to
                from overload.downloads.files import filename_from_url, plan_destination
                try:
                    name = filename_from_url(url) or "fichier"
                    target = plan_destination(dest_dir, name)
                except OverloadError as e:
                    QMessageBox.warning(self, "Erreur", str(e))
                    return
                self.download_status.setText(f"Téléchargement en cours : {name} …")
                self.download_btn.setEnabled(False)
                # Lancement dans un thread simple
                import threading

                def run():
                    try:
                        result = download_to(url, target)
                        # Indexer
                        from overload.library.scanner import scan_file
                        entry = scan_file(result, compute_hash=False)
                        if entry:
                            self.store.upsert_entry(entry)
                            # Classement auto si activé
                            cfg = self.settings.organizer_config()
                            if cfg.enabled:
                                from overload.library.organizer import organize_file
                                try:
                                    root = Path(cfg.base_directory) if cfg.base_directory else dest_dir
                                    new_path = organize_file(result, cfg, root=root, move=True)
                                    entry.path = new_path
                                    entry.filename = new_path.name
                                    self.store.upsert_entry(entry)
                                    # Ancienne entrée (ancien chemin) à supprimer
                                    self.store.remove_entry(result) if result != new_path else None
                                except Exception:
                                    pass
                        self.download_status.setText(f"Terminé : {result.name}")
                    except Exception as e:
                        self.download_status.setText(f"Échec : {e}")
                    finally:
                        self.download_btn.setEnabled(True)
                        # Rafraîchir bibliothèque
                        try:
                            self.library_page.refresh()
                        except Exception:
                            pass

                threading.Thread(target=run, daemon=True).start()

            self.download_btn.clicked.connect(do_download)
            self.stack.addWidget(page)

        def _build_organizer_page(self) -> None:
            page = QScrollArea()
            page.setWidgetResizable(True)
            content = QWidget()
            page.setWidget(content)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            layout.addWidget(QLabel("<h2>⭐ Classement automatique</h2>"))
            layout.addWidget(QLabel("OverLoad peut ranger chaque téléchargement dans un dossier selon son type, son extension ou sa date."))

            cfg = self.settings.organizer_config()

            # Groupe principal
            box = QGroupBox("Dossier de base")
            form = QFormLayout(box)
            self.org_base_input = QLineEdit()
            self.org_base_input.setPlaceholderText(str(Path.home() / "Vidéos" / "OverLoad"))
            self.org_base_input.setText(cfg.base_directory)
            browse = QPushButton("Parcourir…")
            browse.setObjectName("secondary")
            row = QHBoxLayout()
            row.addWidget(self.org_base_input, stretch=1)
            row.addWidget(browse)
            form.addRow("Dossier racine :", row)
            layout.addWidget(box)

            def browse_base():
                d = QFileDialog.getExistingDirectory(self, "Dossier de classement")
                if d:
                    self.org_base_input.setText(d)

            browse.clicked.connect(browse_base)

            # Sous-dossiers par type
            type_box = QGroupBox("Sous-dossiers par type")
            tform = QFormLayout(type_box)
            self.org_video_input = QLineEdit(cfg.folders.get("video", "Vidéos"))
            self.org_audio_input = QLineEdit(cfg.folders.get("audio", "Musiques"))
            self.org_image_input = QLineEdit(cfg.folders.get("image", "Images"))
            self.org_other_input = QLineEdit(cfg.folders.get("other", "Autres"))
            tform.addRow("Vidéos :", self.org_video_input)
            tform.addRow("Musiques :", self.org_audio_input)
            tform.addRow("Images :", self.org_image_input)
            tform.addRow("Autres :", self.org_other_input)
            layout.addWidget(type_box)

            # Date template
            date_box = QGroupBox("Organisation par date")
            dform = QFormLayout(date_box)
            self.org_date_combo = QComboBox()
            self.org_date_combo.addItem("Pas de sous-dossier par date", "")
            self.org_date_combo.addItem("Année / Mois  (2024/10)", "%Y/%m")
            self.org_date_combo.addItem("Année-Mois  (2024-10)", "%Y-%m")
            self.org_date_combo.addItem("Année  (2024)", "%Y")
            idx = self.org_date_combo.findData(cfg.date_template)
            if idx >= 0:
                self.org_date_combo.setCurrentIndex(idx)
            dform.addRow("Structure :", self.org_date_combo)
            self.org_enabled_check = QCheckBox("Activer le classement automatique")
            self.org_enabled_check.setChecked(cfg.enabled)
            dform.addRow(self.org_enabled_check)
            layout.addWidget(date_box)

            # Aperçu
            preview_btn = QPushButton("Aperçu du classement")
            preview_btn.setObjectName("secondary")
            preview_label = QLabel("")
            preview_label.setObjectName("muted")
            preview_label.setWordWrap(True)

            def do_preview():
                tmp_cfg = OrganizerConfig(
                    enabled=self.org_enabled_check.isChecked(),
                    base_directory=self.org_base_input.text().strip(),
                    folders={
                        "video": self.org_video_input.text().strip() or "Vidéos",
                        "audio": self.org_audio_input.text().strip() or "Musiques",
                        "image": self.org_image_input.text().strip() or "Images",
                        "other": self.org_other_input.text().strip() or "Autres",
                    },
                    date_template=self.org_date_combo.currentData() or "",
                )
                base = Path(tmp_cfg.base_directory) if tmp_cfg.base_directory else Path.home() / "OverLoad"
                # Exemples
                import time

                from overload.library.models import MediaEntry, MediaType
                now = time.time()
                examples = [
                    MediaEntry(Path("vacances.mp4"), "vacances.mp4", MediaType.VIDEO, ".mp4", 120_000_000, now),
                    MediaEntry(Path("podcast.mp3"), "podcast.mp3", MediaType.AUDIO, ".mp3", 45_000_000, now),
                    MediaEntry(Path("photo.jpg"), "photo.jpg", MediaType.IMAGE, ".jpg", 5_000_000, now),
                ]
                from overload.library.organizer import preview_organize
                lines = []
                for e, dest in preview_organize(examples, tmp_cfg, base):
                    lines.append(f"• {e.filename} → <code>{dest}</code>")
                preview_label.setText("<br>".join(lines))

            preview_btn.clicked.connect(do_preview)
            layout.addWidget(preview_btn)
            layout.addWidget(preview_label)

            save_btn = QPushButton("Enregistrer")
            layout.addWidget(save_btn)

            def save_org():
                new_cfg = OrganizerConfig(
                    enabled=self.org_enabled_check.isChecked(),
                    base_directory=self.org_base_input.text().strip(),
                    folders={
                        "video": self.org_video_input.text().strip() or "Vidéos",
                        "audio": self.org_audio_input.text().strip() or "Musiques",
                        "image": self.org_image_input.text().strip() or "Images",
                        "other": self.org_other_input.text().strip() or "Autres",
                    },
                    date_template=self.org_date_combo.currentData() or "",
                )
                self.settings.set_organizer_config(new_cfg)
                QMessageBox.information(self, "Enregistré", "Règles de classement mises à jour.")

            save_btn.clicked.connect(save_org)

            layout.addStretch()
            self.stack.addWidget(page)

        def _build_settings_page(self) -> None:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(QLabel("<h2>⚙️ Paramètres</h2>"))

            # Dossier de téléchargement
            dl_box = QGroupBox("Téléchargements")
            form = QFormLayout(dl_box)
            self.dl_dir_input = QLineEdit()
            dl_dir = self.settings.download_dir()
            if dl_dir:
                self.dl_dir_input.setText(str(dl_dir))
            else:
                self.dl_dir_input.setPlaceholderText(str(Path.home() / "Downloads" / "OverLoad"))
            browse = QPushButton("Parcourir…")
            browse.setObjectName("secondary")
            row = QHBoxLayout()
            row.addWidget(self.dl_dir_input, stretch=1)
            row.addWidget(browse)
            form.addRow("Dossier :", row)
            layout.addWidget(dl_box)

            def browse_dl():
                d = QFileDialog.getExistingDirectory(self, "Dossier de téléchargement")
                if d:
                    self.dl_dir_input.setText(d)

            browse.clicked.connect(browse_dl)

            # Thème
            theme_box = QGroupBox("Apparence")
            tform = QFormLayout(theme_box)
            self.theme_combo = QComboBox()
            self.theme_combo.addItem("Système", "system")
            self.theme_combo.addItem("Clair", "light")
            self.theme_combo.addItem("Sombre", "dark")
            cur = self.settings.get("theme", "system")
            idx = self.theme_combo.findData(cur)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
            tform.addRow("Thème :", self.theme_combo)
            layout.addWidget(theme_box)

            # Actions
            save = QPushButton("Enregistrer les paramètres")
            layout.addWidget(save)

            def do_save():
                dl = self.dl_dir_input.text().strip()
                if dl:
                    self.settings.set_download_dir(Path(dl))
                self.settings.set("theme", self.theme_combo.currentData())
                # Appliquer thème immédiatement
                from PySide6.QtWidgets import QApplication

                from overload.ui.styles import apply_theme
                apply_theme(QApplication.instance(), self.theme_combo.currentData())
                QMessageBox.information(self, "Enregistré", "Paramètres mis à jour. Redémarrage conseillé pour le thème.")

            save.clicked.connect(do_save)

            # Nettoyage
            clean_btn = QPushButton("Retirer les entrées manquantes de la bibliothèque")
            clean_btn.setObjectName("secondary")
            def clean():
                n = self.store.remove_missing()
                QMessageBox.information(self, "Nettoyage", f"{n} entrée(s) retirée(s).")
                try:
                    self.library_page.refresh()
                except Exception:
                    pass
            clean_btn.clicked.connect(clean)
            layout.addWidget(clean_btn)

            layout.addStretch()
            self.stack.addWidget(page)

        def _build_about_page(self) -> None:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(QLabel("<h2>ℹ️ À propos</h2>"))
            layout.addWidget(QLabel(
                "<b>OverLoad</b> — Organise et prépare tes médias.<br>"
                "Version 0.1 — Bibliothèque intégrée.<br><br>"
                "Fonctionnalités : vignettes, recherche et filtres (type, taille, date, durée), "
                "détection des doublons (sans suppression automatique), classement auto dans des dossiers "
                "personnalisables, prévisualisation et ouverture de l'emplacement.<br><br>"
                "<b>Le plus</b> : la recherche par texte + filtre de date permet de retrouver un fichier "
                "téléchargé il y a plusieurs mois en quelques secondes.<br><br>"
                "Sources en v1 : adresses HTTP(S) directes uniquement, sans contournement de protections.<br>"
                "Licence : MIT — voir LICENSE et THIRD_PARTY_LICENSES.md"
            ))
            open_data = QPushButton("Ouvrir le dossier de données")
            open_data.setObjectName("secondary")
            def do_open():
                p = app_data_dir()
                from overload.library.preview import open_media
                try:
                    import platform
                    import subprocess
                    if platform.system() == "Windows":
                        subprocess.Popen(["explorer", str(p)])
                    else:
                        open_media(p)
                except Exception:
                    QMessageBox.information(self, "Dossier de données", str(p))
            open_data.clicked.connect(do_open)
            layout.addWidget(open_data)
            layout.addStretch()
            self.stack.addWidget(page)

        def _switch_page(self, index: int) -> None:
            self.stack.setCurrentIndex(index)

        def closeEvent(self, event) -> None:  # noqa: N802
            try:
                self.store.close()
            except Exception:
                pass
            super().closeEvent(event)

else:
    class MainWindow:  # type: ignore
        pass
