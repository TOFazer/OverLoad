"""Onglet « Espace Créateurs » : projets vidéo, médias, renommage, sous-titres, inventaire.

L'interface pilote exclusivement le paquet `overload.creators` ; aucune logique
métier ne réside ici. Les travaux coûteux (FFprobe, copies, extractions) sont
exécutés hors du thread graphique, avec résultats collectés via une file.

Règles affichées et appliquées partout :
- les fichiers d'origine ne sont jamais déplacés, renommés ni supprimés ;
- aucune copie n'est effectuée sans confirmation explicite ;
- aucune destination existante n'est écrasée.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes
from overload.core.paths import open_folder
from overload.creators.models import EditingProfile, PlannedCopy
from overload.creators.renaming import (
    DEFAULT_TEMPLATE,
    TEMPLATE_HELP,
    apply_renaming,
    preview_renaming,
)
from overload.creators.scan import export_inventory_csv, scan_tree
from overload.creators.structure import (
    README_FILENAME,
    create_project_structure,
    execute_import,
    plan_import,
)
from overload.creators.subtitles import (
    create_srt_template,
    extract_audio_track,
    extract_subtitle_track,
    probe_tracks,
)
from overload.creators.workspace import CreatorsWorkspace
from overload.downloads.duplicates import DuplicatePolicy

SAFETY_NOTE = (
    "🛡 Protection des originaux : rien n'est déplacé, renommé ou supprimé sur vos fichiers "
    "d'origine — seules des copies sont créées, après votre confirmation, et aucun fichier "
    "existant n'est jamais écrasé."
)


def _parse_paths(text: str) -> list[Path]:
    """Analyse une zone « un chemin par ligne » en ignorant commentaires et lignes vides."""
    paths: list[Path] = []
    for line in text.splitlines():
        cleaned = line.strip().strip('"')
        if not cleaned or cleaned.startswith("#"):
            continue
        paths.append(Path(cleaned))
    return paths


def create_creators_widget(
    *,
    history: Any = None,
    data_dir: Path | None = None,
):
    """Construit l'onglet complet « Espace Créateurs » (Qt Widgets)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    workspace = CreatorsWorkspace(data_dir)
    widget = QWidget()
    root_layout = QVBoxLayout(widget)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(10)

    header = QLabel("🎬 Espace Créateurs")
    header.setObjectName("sectionTitle")
    root_layout.addWidget(header)
    subtitle = QLabel(
        "Préparez un dossier complet pour chaque projet vidéo, importez et organisez vos "
        "médias, renommez par lots, gérez sous-titres et pistes, exportez l'inventaire."
    )
    subtitle.setObjectName("mutedLabel")
    subtitle.setWordWrap(True)
    root_layout.addWidget(subtitle)
    safety_lbl = QLabel(SAFETY_NOTE)
    safety_lbl.setObjectName("mutedLabel")
    safety_lbl.setWordWrap(True)
    root_layout.addWidget(safety_lbl)

    tabs = QTabWidget()
    tabs.setObjectName("creatorsTabs")
    root_layout.addWidget(tabs, stretch=1)

    def _safe(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except OverloadError as exc:
            QMessageBox.warning(widget, "OverLoad — Espace Créateurs", str(exc))
            return None

    def _report_error(exc: BaseException) -> None:
        """Présente une erreur survenue dans un travail en arrière-plan."""
        if isinstance(exc, OverloadError):
            QMessageBox.warning(widget, "OverLoad — Espace Créateurs", str(exc))
        else:
            QMessageBox.warning(
                widget,
                "OverLoad — Espace Créateurs",
                f"Erreur inattendue : {exc}",
            )

    def _launch_job(
        fn: Callable[[Callable[[str], None]], Any],
        on_done: Callable[[str, Any], None],
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """Exécute `fn` hors du thread graphique ; `on_done(kind, payload)` récupère le résultat."""
        results: queue.Queue = queue.Queue()

        def work() -> None:
            try:
                outcome = fn(lambda msg: results.put(("progress", msg)))
                results.put(("done", outcome))
            except BaseException as exc:  # noqa: BLE001
                results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()
        timer = QTimer(widget)
        timer.setInterval(80)

        def collect() -> None:
            try:
                kind, payload = results.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                if on_progress is not None:
                    on_progress(str(payload))
                return
            timer.stop()
            on_done(kind, payload)

        timer.timeout.connect(collect)
        timer.start()

    def _download_sources() -> dict[str, str]:
        """Carte chemin → adresse source, reconstituée depuis l'historique des téléchargements."""
        if history is None:
            return {}
        mapping: dict[str, str] = {}
        try:
            for entry in history.list_entries(limit=1000):
                if entry.url:
                    mapping.setdefault(str(Path(entry.destination_path)), entry.url)
        except Exception:  # noqa: BLE001
            return {}
        return mapping

    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("panelCard")
        return card

    # ------------------------------------------------------------------
    # 1. Mes projets
    # ------------------------------------------------------------------
    def build_projects_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(10)

        form_card = _card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_title = QLabel("➕ Préparer un nouveau projet vidéo")
        form_title.setObjectName("sectionTitle")
        form_layout.addWidget(form_title)

        row1 = QHBoxLayout()
        name_edit = QLineEdit()
        name_edit.setObjectName("creatorsProjectName")
        name_edit.setPlaceholderText("Nom du projet (ex. Vlog octobre 2026)")
        name_edit.setMinimumWidth(240)
        parent_edit = QLineEdit()
        parent_edit.setObjectName("creatorsProjectParent")
        parent_edit.setPlaceholderText("Dossier parent (ex. C:\\Users\\vous\\Videos)")
        browse_parent_btn = QPushButton("📂 Parcourir…")
        profile_combo = QComboBox()
        profile_combo.setObjectName("creatorsProjectProfile")
        row1.addWidget(QLabel("Nom :"))
        row1.addWidget(name_edit, stretch=1)
        row1.addWidget(QLabel("Dossier parent :"))
        row1.addWidget(parent_edit, stretch=1)
        row1.addWidget(browse_parent_btn)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        create_btn = QPushButton("🗂 Créer le dossier du projet")
        create_btn.setObjectName("creatorsProjectCreate")
        create_btn.setProperty("primary", True)
        row2.addWidget(QLabel("Profil de montage :"))
        row2.addWidget(profile_combo, stretch=1)
        row2.addStretch()
        row2.addWidget(create_btn)
        form_layout.addLayout(row2)
        note = QLabel(
            "La structure complète (rushs, audio, images, sous-titres, projets, exports) est "
            f"créée d'un coup, avec un fichier {README_FILENAME} et un manifeste de règles. "
            "Un dossier existant est enrichi, jamais vidé ni écrasé."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        form_layout.addWidget(note)
        layout.addWidget(form_card)

        list_title = QLabel("📚 Projets enregistrés")
        list_title.setObjectName("sectionTitle")
        layout.addWidget(list_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("creatorsProjectList")
        container = QWidget()
        list_layout = QVBoxLayout(container)
        list_layout.setContentsMargins(0, 0, 4, 0)
        list_layout.setSpacing(8)
        empty_lbl = QLabel("Aucun projet pour l'instant. Créez-en un ci-dessus pour démarrer.")
        empty_lbl.setObjectName("mutedLabel")
        list_layout.addWidget(empty_lbl)
        list_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        state = {"widgets": []}

        def refresh_profiles() -> None:
            profile_combo.clear()
            prefs = workspace.preferences()
            selected = prefs.get("last_profile_id", "universel")
            for profile in workspace.profiles.list_profiles():
                label = profile.name + ("" if profile.builtin else " (perso)")
                profile_combo.addItem(label, profile.id)
                if profile.id == selected:
                    profile_combo.setCurrentIndex(profile_combo.count() - 1)

        def refresh_projects() -> None:
            for entry in state["widgets"]:
                entry.deleteLater()
            state["widgets"] = []
            projects = workspace.projects.list_projects()
            empty_lbl.setVisible(not projects)
            for position, project in enumerate(projects):
                card = QFrame()
                card.setObjectName("itemCard")
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(12, 8, 12, 8)
                info_col = QVBoxLayout()
                title_row = QHBoxLayout()
                name_lbl = QLabel(project.name)
                name_lbl.setStyleSheet("font-weight: 700;")
                title_row.addWidget(name_lbl)
                title_row.addStretch()
                info_col.addLayout(title_row)
                try:
                    profile = workspace.profiles.get(project.profile_id)
                    profile_txt = profile.name
                except OverloadError:
                    profile_txt = f"profil « {project.profile_id} » inconnu"
                meta = QLabel(
                    f"{project.root_dir} · Profil : {profile_txt} · "
                    f"Créé le {project.created_at[:10]}"
                )
                meta.setObjectName("mutedLabel")
                info_col.addWidget(meta)
                card_layout.addLayout(info_col, stretch=1)

                open_btn = QPushButton("📁 Ouvrir")
                def _open_project(pid: str = project.id) -> None:
                    _safe(
                        lambda: (
                            workspace.projects.touch(pid),
                            open_folder(workspace.projects.get(pid).path),
                        )
                    )

                open_btn.clicked.connect(
                    lambda _checked=False, pid=project.id: _open_project(pid)
                )
                remove_btn = QPushButton("Retirer de la liste")
                remove_btn.clicked.connect(
                    lambda _checked=False, pid=project.id: _confirm_remove_project(pid)
                )
                card_layout.addWidget(open_btn)
                card_layout.addWidget(remove_btn)
                list_layout.insertWidget(position, card)
                state["widgets"].append(card)

        def _confirm_remove_project(project_id: str) -> None:
            answer = QMessageBox.question(
                widget,
                "Retirer ce projet ?",
                "Retirer ce projet de la liste OverLoad ?\n\n"
                "Aucun fichier ni dossier ne sera supprimé sur le disque : le dossier du "
                "projet reste exactement où il est.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                workspace.projects.remove_project(project_id)
                refresh_projects()

        def on_browse_parent() -> None:
            videos = Path.home() / "Videos"
            start = parent_edit.text().strip() or (
                str(videos) if videos.is_dir() else str(Path.home())
            )
            folder = QFileDialog.getExistingDirectory(widget, "Dossier parent du projet", start)
            if folder:
                parent_edit.setText(folder)

        def on_create() -> None:
            from overload.creators.fsutil import sanitize_name

            raw_name = name_edit.text().strip()
            if not raw_name:
                QMessageBox.warning(widget, "Nom manquant", "Saisissez d'abord un nom de projet.")
                return
            parent = Path(parent_edit.text().strip() or str(Path.home() / "Videos"))
            if not parent.is_dir():
                QMessageBox.warning(
                    widget,
                    "Dossier parent introuvable",
                    f"Le dossier « {parent} » n'existe pas. Choisissez un dossier existant.",
                )
                return
            name = sanitize_name(raw_name)
            root = parent / name
            if root.exists() and any(root.iterdir()):
                answer = QMessageBox.question(
                    widget,
                    "Le dossier existe déjà",
                    f"Le dossier « {root} » existe déjà et n'est pas vide.\n\n"
                    "OverLoad peut y ajouter la structure du projet sans rien supprimer ni "
                    "écraser. Continuer ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            profile_id = str(profile_combo.currentData() or "universel")
            created = _safe(
                lambda: create_project_structure(
                    root, project_name=name, profile=workspace.profiles.get(profile_id)
                )
            )
            if created is None:
                return
            workspace.projects.add_project(name=name, root_dir=root, profile_id=profile_id)
            workspace.update_preferences(last_profile_id=profile_id)
            refresh_projects()
            QMessageBox.information(
                widget,
                "Projet prêt",
                f"Le dossier du projet « {name} » est prêt :\n{root}\n\n"
                f"{len(created)} sous-dossier(s) créé(s), LISEZ-MOI et manifeste en place.\n"
                "Vous pouvez maintenant y organiser vos médias depuis « Préparer mon projet ».",
            )

        browse_parent_btn.clicked.connect(on_browse_parent)
        create_btn.clicked.connect(on_create)
        refresh_profiles()
        refresh_projects()
        return page

    # ------------------------------------------------------------------
    # 2. Préparer mon projet (import / organisation des médias)
    # ------------------------------------------------------------------
    def build_prepare_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(10)

        sources_card = _card()
        sources_layout = QVBoxLayout(sources_card)
        sources_layout.setContentsMargins(12, 10, 12, 10)
        src_title = QLabel("1️⃣ Vos médias d'origine (fichiers ou dossiers entiers)")
        src_title.setObjectName("sectionTitle")
        sources_layout.addWidget(src_title)
        sources_edit = QPlainTextEdit()
        sources_edit.setObjectName("creatorsPrepareSources")
        sources_edit.setPlaceholderText(
            "Collez des chemins de fichiers ou de dossiers (un par ligne), ou utilisez les "
            "boutons ci-dessous. Les commentaires # sont ignorés."
        )
        sources_edit.setMaximumHeight(110)
        sources_layout.addWidget(sources_edit)
        src_buttons = QHBoxLayout()
        add_files_btn = QPushButton("➕ Ajouter des fichiers…")
        add_folder_btn = QPushButton("➕ Ajouter un dossier…")
        clear_sources_btn = QPushButton("🗑 Vider")
        src_buttons.addWidget(add_files_btn)
        src_buttons.addWidget(add_folder_btn)
        src_buttons.addWidget(clear_sources_btn)
        src_buttons.addStretch()
        sources_layout.addLayout(src_buttons)
        layout.addWidget(sources_card)

        dest_card = _card()
        dest_layout = QVBoxLayout(dest_card)
        dest_layout.setContentsMargins(12, 10, 12, 10)
        dest_title = QLabel("2️⃣ Destination : un de vos projets, ou un nouveau dossier")
        dest_title.setObjectName("sectionTitle")
        dest_layout.addWidget(dest_title)
        dest_row = QHBoxLayout()
        project_combo = QComboBox()
        project_combo.setObjectName("creatorsPrepareProject")
        project_combo.addItem("— Nouveau dossier —", "")
        dest_edit = QLineEdit()
        dest_edit.setObjectName("creatorsPrepareFolder")
        dest_edit.setPlaceholderText("Dossier de destination du projet…")
        browse_dest_btn = QPushButton("📂 Parcourir…")
        dest_row.addWidget(QLabel("Projet :"))
        dest_row.addWidget(project_combo, stretch=1)
        dest_row.addWidget(dest_edit, stretch=1)
        dest_row.addWidget(browse_dest_btn)
        dest_layout.addLayout(dest_row)

        options_row = QHBoxLayout()
        classify_chk = QCheckBox("Classer par type (rushs / audio / images / sous-titres)")
        classify_chk.setObjectName("creatorsPrepareClassify")
        classify_chk.setChecked(True)
        rename_chk = QCheckBox("Renommer selon un modèle :")
        rename_chk.setObjectName("creatorsPrepareRename")
        template_edit = QLineEdit()
        template_edit.setObjectName("creatorsPrepareTemplate")
        template_edit.setText(str(workspace.preferences().get("rename_template", DEFAULT_TEMPLATE)))
        template_edit.setMinimumWidth(260)
        options_row.addWidget(classify_chk)
        options_row.addSpacing(12)
        options_row.addWidget(rename_chk)
        options_row.addWidget(template_edit, stretch=1)
        dest_layout.addLayout(options_row)
        template_help = QLabel(TEMPLATE_HELP)
        template_help.setObjectName("mutedLabel")
        dest_layout.addWidget(template_help)
        layout.addWidget(dest_card)

        plan_card = _card()
        plan_layout = QVBoxLayout(plan_card)
        plan_layout.setContentsMargins(12, 10, 12, 10)
        plan_title = QLabel("3️⃣ Plan puis copie contrôlée")
        plan_title.setObjectName("sectionTitle")
        plan_layout.addWidget(plan_title)
        plan_buttons = QHBoxLayout()
        plan_btn = QPushButton("🔍 Préparer le plan (rien n'est copié)")
        plan_btn.setObjectName("creatorsPreparePlan")
        run_btn = QPushButton("✅ Copier les fichiers")
        run_btn.setObjectName("creatorsPrepareRun")
        run_btn.setEnabled(False)
        open_dest_btn = QPushButton("📁 Ouvrir la destination")
        open_dest_btn.setEnabled(False)
        plan_buttons.addWidget(plan_btn)
        plan_buttons.addWidget(run_btn)
        plan_buttons.addWidget(open_dest_btn)
        plan_buttons.addStretch()
        plan_layout.addLayout(plan_buttons)
        plan_summary = QLabel("Le plan montre où chaque copie arrivera, avant toute action.")
        plan_summary.setObjectName("mutedLabel")
        plan_summary.setWordWrap(True)
        plan_layout.addWidget(plan_summary)
        preview_edit = QPlainTextEdit()
        preview_edit.setObjectName("creatorsPreparePreview")
        preview_edit.setReadOnly(True)
        plan_layout.addWidget(preview_edit, stretch=1)
        layout.addWidget(plan_card, stretch=1)

        state: dict[str, Any] = {"plan": None, "dest": None}

        def refresh_projects_combo() -> None:
            project_combo.blockSignals(True)
            project_combo.clear()
            project_combo.addItem("— Nouveau dossier —", "")
            for project in workspace.projects.list_projects():
                project_combo.addItem(project.name, project.id)
            project_combo.blockSignals(False)

        def on_project_chosen(index: int) -> None:
            project_id = str(project_combo.itemData(index) or "")
            if not project_id:
                return
            project = workspace.projects.get(project_id)
            dest_edit.setText(str(project.path))

        def on_add_files() -> None:
            files, _ = QFileDialog.getOpenFileNames(
                widget, "Choisir les médias à organiser", "", "Médias (*.*)"
            )
            if files:
                _append_paths(sources_edit, files)

        def on_add_folder() -> None:
            folder = QFileDialog.getExistingDirectory(widget, "Choisir un dossier de médias")
            if folder:
                _append_paths(sources_edit, [folder])

        def _append_paths(edit: QPlainTextEdit, paths: list[str]) -> None:
            current = edit.toPlainText().strip()
            extra = "\n".join(paths)
            edit.setPlainText(f"{current}\n{extra}".strip() if current else extra)

        def _resolve_destination() -> tuple[Path, EditingProfile, str] | None:
            dest_text = dest_edit.text().strip()
            if not dest_text:
                QMessageBox.warning(
                    widget,
                    "Destination manquante",
                    "Choisissez un projet ou un dossier de destination.",
                )
                return None
            root = Path(dest_text)
            profile = workspace.profiles.default_profile()
            project_name = ""
            for project in workspace.projects.list_projects():
                if project.path == root:
                    try:
                        profile = workspace.profiles.get(project.profile_id)
                    except OverloadError:
                        profile = workspace.profiles.default_profile()
                    project_name = project.name
                    break
            return root, profile, project_name or root.name

        def on_plan() -> None:
            resolved = _resolve_destination()
            if resolved is None:
                return
            root, profile, project_name = resolved
            sources = _parse_paths(sources_edit.toPlainText())
            if not sources:
                QMessageBox.warning(
                    widget, "Aucun média", "Ajoutez d'abord des fichiers ou dossiers à organiser."
                )
                return
            template = None
            if rename_chk.isChecked():
                template = template_edit.text().strip() or None
                if template:
                    workspace.update_preferences(rename_template=template)

            def job(_report: Callable[[str], None]) -> list[PlannedCopy]:
                return plan_import(
                    sources,
                    root,
                    profile,
                    project_name=project_name,
                    rename_template=template,
                    classify=classify_chk.isChecked(),
                )

            def done(kind: str, payload: Any) -> None:
                plan_btn.setEnabled(True)
                if kind == "error":
                    _report_error(payload)
                    return
                plan = payload
                state["plan"] = plan
                state["dest"] = root
                lines = []
                for step in plan:
                    marker = "⚠ existe déjà" if step.collision else "✓"
                    lines.append(f"{marker}  {step.source}  →  {step.destination}")
                collisions = sum(1 for step in plan if step.collision)
                preview_edit.setPlainText(
                    "\n".join(lines) or "Aucun média trouvé dans la sélection."
                )
                plan_summary.setText(
                    f"{len(plan)} média(s) planifié(s) · {len(plan) - collisions} prêt(s) · "
                    f"{collisions} en conflit (à confirmer). Destination : {root}"
                )
                run_btn.setEnabled(bool(plan))
                open_dest_btn.setEnabled(True)

            plan_btn.setEnabled(False)
            _launch_job(job, done)

        def on_run() -> None:
            plan = state["plan"]
            if not plan:
                return
            collisions = [step for step in plan if step.collision]
            answer = QMessageBox.question(
                widget,
                "Confirmer la copie",
                f"Copier {len(plan)} fichier(s) vers « {state['dest']} » ?\n\n"
                "Vos fichiers d'origine ne seront ni déplacés ni modifiés : seules des copies "
                "sont créées.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            policy = DuplicatePolicy.RENAME
            if collisions:
                box = QMessageBox(widget)
                box.setWindowTitle("Destinations déjà présentes")
                box.setText(
                    f"{len(collisions)} destination(s) existent déjà.\n\n"
                    "Comment traiter ces fichiers ? Aucun fichier existant ne sera écrasé."
                )
                rename_choice = box.addButton(
                    "Créer une copie « (2) »", QMessageBox.ButtonRole.AcceptRole
                )
                skip_choice = box.addButton(
                    "Ignorer ces fichiers", QMessageBox.ButtonRole.ActionRole
                )
                box.addButton("Annuler tout", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                clicked = box.clickedButton()
                if clicked == rename_choice:
                    policy = DuplicatePolicy.RENAME
                elif clicked == skip_choice:
                    policy = DuplicatePolicy.SKIP
                else:
                    return

            def job(report: Callable[[str], None]) -> Any:
                result = execute_import(plan, collision_policy=policy)
                report(f"Copies terminées : {len(result.copied)} réussie(s).")
                return result

            def done(kind: str, payload: Any) -> None:
                run_btn.setEnabled(True)
                if kind == "error":
                    _report_error(payload)
                    return
                result = payload
                failed_lines = "\n".join(
                    f"  {src.name} : {err}" for src, err in result.failed[:5]
                )
                summary = (
                    f"✅ {len(result.copied)} copie(s) créée(s) · "
                    f"{len(result.skipped)} ignorée(s) · "
                    f"{len(result.failed)} échec(s)."
                )
                if result.failed:
                    summary += "\nÉchecs :\n" + failed_lines
                plan_summary.setText(summary)
                preview_edit.setPlainText(
                    "\n".join(f"✓ {src}  →  {dst}" for src, dst in result.copied)
                    + "\n"
                    + "\n".join(
                        f"– {src.name} : {reason}" for src, reason in result.skipped
                    )
                )

            run_btn.setEnabled(False)
            _launch_job(job, done, on_progress=lambda msg: plan_summary.setText(msg))

        def on_open_dest() -> None:
            if state["dest"] is not None:
                _safe(lambda: open_folder(state["dest"]))

        project_combo.currentIndexChanged.connect(on_project_chosen)
        add_files_btn.clicked.connect(on_add_files)
        add_folder_btn.clicked.connect(on_add_folder)
        clear_sources_btn.clicked.connect(sources_edit.clear)
        browse_dest_btn.clicked.connect(
            lambda: dest_edit.setText(
                QFileDialog.getExistingDirectory(widget, "Dossier de destination", dest_edit.text())
                or dest_edit.text()
            )
        )
        plan_btn.clicked.connect(on_plan)
        run_btn.clicked.connect(on_run)
        open_dest_btn.clicked.connect(on_open_dest)
        refresh_projects_combo()
        page_refreshers[1] = refresh_projects_combo
        return page

    # ------------------------------------------------------------------
    # 3. Renommer par lots
    # ------------------------------------------------------------------
    def build_rename_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(10)

        sources_card = _card()
        sources_layout = QVBoxLayout(sources_card)
        sources_layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("✏️ Renommer des lots de fichiers")
        title.setObjectName("sectionTitle")
        sources_layout.addWidget(title)
        sources_edit = QPlainTextEdit()
        sources_edit.setObjectName("creatorsRenameSources")
        sources_edit.setPlaceholderText(
            "Chemins des fichiers à renommer, un par ligne (collez-les ou utilisez les boutons)."
        )
        sources_edit.setMaximumHeight(110)
        sources_layout.addWidget(sources_edit)
        buttons = QHBoxLayout()
        add_files_btn = QPushButton("➕ Ajouter des fichiers…")
        add_folder_btn = QPushButton("➕ Ajouter un dossier…")
        clear_btn = QPushButton("🗑 Vider")
        buttons.addWidget(add_files_btn)
        buttons.addWidget(add_folder_btn)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        sources_layout.addLayout(buttons)
        layout.addWidget(sources_card)

        template_card = _card()
        template_layout = QVBoxLayout(template_card)
        template_layout.setContentsMargins(12, 10, 12, 10)
        template_row = QHBoxLayout()
        project_edit = QLineEdit()
        project_edit.setObjectName("creatorsRenameProject")
        project_edit.setPlaceholderText("Nom du projet (pour le jeton {projet})")
        template_edit = QLineEdit()
        template_edit.setObjectName("creatorsRenameTemplate")
        template_edit.setText(str(workspace.preferences().get("rename_template", DEFAULT_TEMPLATE)))
        template_row.addWidget(QLabel("Projet :"))
        template_row.addWidget(project_edit, 1)
        template_row.addWidget(QLabel("Modèle :"))
        template_row.addWidget(template_edit, 2)
        template_layout.addLayout(template_row)
        help_lbl = QLabel(TEMPLATE_HELP)
        help_lbl.setObjectName("mutedLabel")
        help_lbl.setWordWrap(True)
        template_layout.addWidget(help_lbl)
        policy_row = QHBoxLayout()
        policy_combo = QComboBox()
        policy_combo.setObjectName("creatorsRenamePolicy")
        policy_combo.addItem("En conflit : ajouter « (2) », « (3) »… (rien n'est écrasé)", "rename")
        policy_combo.addItem("En conflit : laisser le fichier intact", "skip")
        apply_btn = QPushButton("✅ Renommer les fichiers")
        apply_btn.setObjectName("creatorsRenameApply")
        policy_row.addWidget(QLabel("Conflits :"))
        policy_row.addWidget(policy_combo, stretch=1)
        policy_row.addWidget(apply_btn)
        template_layout.addLayout(policy_row)
        layout.addWidget(template_card)

        preview_card = _card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_lbl = QLabel(
            "Aperçu en direct (aucun fichier modifié tant que vous ne confirmez pas)"
        )
        preview_lbl.setObjectName("creatorsRenameStatus")
        preview_layout.addWidget(preview_lbl)
        preview_edit = QPlainTextEdit()
        preview_edit.setObjectName("creatorsRenamePreview")
        preview_edit.setReadOnly(True)
        preview_layout.addWidget(preview_edit, stretch=1)
        layout.addWidget(preview_card, stretch=1)

        def current_files() -> list[Path]:
            from overload.creators.fsutil import expand_sources

            return expand_sources(_parse_paths(sources_edit.toPlainText()))

        def refresh_preview() -> None:
            files = current_files()
            if not files:
                preview_edit.setPlainText("")
                return
            steps = preview_renaming(
                files, template_edit.text(), project_name=project_edit.text().strip()
            )
            lines = []
            for step in steps:
                if step.status == "ok":
                    lines.append(f"✓ {step.original.name}  →  {step.new_path.name}")
                elif step.status == "conflit":
                    lines.append(
                        f"⚠ {step.original.name}  →  {step.new_path.name} ({step.message})"
                    )
                elif step.status == "inchangé":
                    lines.append(f"= {step.original.name} (inchangé)")
                else:
                    lines.append(f"✕ {step.original.name} — {step.message.splitlines()[0]}")
            preview_edit.setPlainText("\n".join(lines))

        def on_apply() -> None:
            files = current_files()
            if not files:
                QMessageBox.warning(
                    widget, "Aucun fichier", "Ajoutez d'abord des fichiers à renommer."
                )
                return
            template = template_edit.text().strip()
            workspace.update_preferences(rename_template=template)
            answer = QMessageBox.question(
                widget,
                "Confirmer le renommage",
                f"Renommer {len(files)} fichier(s) selon le modèle « {template} » ?\n\n"
                "Aucun fichier existant ne sera écrasé ; en cas de conflit, un suffixe "
                "« (2) », « (3) »… est ajouté ou le fichier est laissé intact selon votre choix.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            policy = (
                DuplicatePolicy.SKIP
                if str(policy_combo.currentData()) == "skip"
                else DuplicatePolicy.RENAME
            )

            def job(report: Callable[[str], None]) -> Any:
                result = apply_renaming(
                    files,
                    template,
                    project_name=project_edit.text().strip(),
                    conflict_policy=policy,
                )
                report(f"Renommage terminé : {len(result.renamed)} fichier(s).")
                return result

            def done(kind: str, payload: Any) -> None:
                apply_btn.setEnabled(True)
                if kind == "error":
                    preview_lbl.setText("Renommage impossible.")
                    _report_error(payload)
                    return
                result = payload
                remaining = [src for src, _ in result.renamed]
                new_names = [dst for _, dst in result.renamed]
                # Remplace la liste par les nouveaux chemins pour un nouvel aperçu.
                kept = [
                    p for p in _parse_paths(sources_edit.toPlainText()) if p not in remaining
                ]
                sources_edit.setPlainText("\n".join(str(p) for p in kept + new_names))
                preview_lbl.setText(
                    f"✅ {len(result.renamed)} fichier(s) renommé(s) · "
                    f"{len(result.skipped)} laissé(s) intact(s) · "
                    f"{len(result.failed)} échec(s)"
                )
                refresh_preview()

            apply_btn.setEnabled(False)
            _launch_job(job, done, on_progress=lambda msg: preview_lbl.setText(msg))

        def _append_paths(paths: list[str]) -> None:
            current = sources_edit.toPlainText().strip()
            extra = "\n".join(paths)
            sources_edit.setPlainText(f"{current}\n{extra}".strip() if current else extra)

        add_files_btn.clicked.connect(
            lambda: _append_paths(
                QFileDialog.getOpenFileNames(widget, "Choisir des fichiers", "", "Tous (*.*)")[0]
            )
        )
        add_folder_btn.clicked.connect(
            lambda: _append_paths(
                [QFileDialog.getExistingDirectory(widget, "Choisir un dossier")] or []
            )
        )
        clear_btn.clicked.connect(sources_edit.clear)
        sources_edit.textChanged.connect(refresh_preview)
        template_edit.textChanged.connect(refresh_preview)
        project_edit.textChanged.connect(refresh_preview)
        apply_btn.clicked.connect(on_apply)
        return page

    # ------------------------------------------------------------------
    # 4. Sous-titres & pistes
    # ------------------------------------------------------------------
    def build_tracks_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(10)

        media_card = _card()
        media_layout = QVBoxLayout(media_card)
        media_layout.setContentsMargins(12, 10, 12, 10)
        media_title = QLabel("💬 Sous-titres et pistes disponibles")
        media_title.setObjectName("sectionTitle")
        media_layout.addWidget(media_title)
        media_row = QHBoxLayout()
        media_edit = QLineEdit()
        media_edit.setObjectName("creatorsTracksPath")
        media_edit.setPlaceholderText("Choisissez un fichier vidéo ou audio…")
        browse_media_btn = QPushButton("📂 Parcourir…")
        list_btn = QPushButton("🔍 Lister les pistes")
        list_btn.setObjectName("creatorsTracksList")
        media_row.addWidget(media_edit, stretch=1)
        media_row.addWidget(browse_media_btn)
        media_row.addWidget(list_btn)
        media_layout.addLayout(media_row)
        dest_row = QHBoxLayout()
        dest_edit = QLineEdit()
        dest_edit.setObjectName("creatorsTracksDest")
        dest_edit.setPlaceholderText("Dossier des fichiers extraits (par défaut : celui du média)")
        browse_dest_btn = QPushButton("📂 Choisir…")
        dest_row.addWidget(dest_edit, stretch=1)
        dest_row.addWidget(browse_dest_btn)
        media_layout.addLayout(dest_row)
        layout.addWidget(media_card)

        actions_card = _card()
        actions_layout = QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(12, 10, 12, 10)
        select_row = QHBoxLayout()
        track_combo = QComboBox()
        track_combo.setObjectName("creatorsTracksSelect")
        select_row.addWidget(QLabel("Piste :"))
        select_row.addWidget(track_combo, stretch=1)
        srt_btn = QPushButton("💬 Extraire en .srt")
        srt_btn.setObjectName("creatorsTracksSrt")
        wav_btn = QPushButton("🎵 Extraire l'audio en .wav")
        wav_btn.setObjectName("creatorsTracksWav")
        template_btn = QPushButton("📄 Créer un modèle de sous-titres")
        template_btn.setObjectName("creatorsTracksTemplate")
        select_row.addWidget(srt_btn)
        select_row.addWidget(wav_btn)
        actions_layout.addLayout(select_row)
        actions_layout.addWidget(template_btn)
        note = QLabel(
            "L'extraction convertit la piste choisie en .srt (sous-titres) ou .wav (audio PCM) "
            "dans un nouveau fichier : le média d'origine n'est jamais modifié. Le modèle .srt "
            "est un squelette prêt à compléter, encodé en UTF-8."
        )
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        actions_layout.addWidget(note)
        layout.addWidget(actions_card)

        status_lbl = QLabel("Choisissez un média puis listez ses pistes.")
        status_lbl.setObjectName("mutedLabel")
        layout.addWidget(status_lbl)
        output_edit = QPlainTextEdit()
        output_edit.setObjectName("creatorsTracksOutput")
        output_edit.setReadOnly(True)
        layout.addWidget(output_edit, stretch=1)

        state: dict[str, Any] = {"report": None}

        def on_browse_media() -> None:
            filename, _ = QFileDialog.getOpenFileName(widget, "Choisir un média", "", "Tous (*.*)")
            if filename:
                media_edit.setText(filename)
                if not dest_edit.text().strip():
                    dest_edit.setText(str(Path(filename).parent))

        def on_list() -> None:
            media = media_edit.text().strip()
            if not media:
                QMessageBox.warning(
                    widget, "Aucun média", "Choisissez d'abord un fichier."
                )
                return
            list_btn.setEnabled(False)
            status_lbl.setText("Analyse des pistes en cours…")

            def job(_report: Callable[[str], None]) -> Any:
                return probe_tracks(media)

            def done(kind: str, payload: Any) -> None:
                list_btn.setEnabled(True)
                if kind == "error":
                    status_lbl.setText("Analyse impossible.")
                    _report_error(payload)
                    return
                report = payload
                state["report"] = report
                track_combo.clear()
                lines = [
                    f"Fichier : {report.path.name}",
                    f"Conteneur : {report.container or 'inconnu'}",
                    f"Durée : {report.duration_seconds or '—'} s",
                    "",
                    f"PISTES DISPONIBLES — {report.summary()}",
                    "",
                ]
                for track in report.tracks:
                    combo_label = (
                        f"{track.kind_label} #{track.kind_index + 1} — {track.codec}"
                        + (f" ({track.language})" if track.language else "")
                    )
                    track_combo.addItem(combo_label, (track.kind, track.kind_index))
                    lines.append(f"  • {track.summary()}")
                    if track.title:
                        lines.append(f"      Titre : {track.title}")
                if not report.tracks:
                    lines.append("  (aucune piste reconnue)")
                output_edit.setPlainText("\n".join(lines))
                status_lbl.setText(
                    f"{len(report.tracks)} piste(s) trouvée(s). "
                    "Choisissez-en une pour l'extraire."
                )

            _launch_job(job, done)

        def _selected_track() -> tuple[str, int] | None:
            data = track_combo.currentData()
            if data is None:
                QMessageBox.warning(
                    widget, "Aucune piste", "Listez d'abord les pistes puis choisissez-en une."
                )
                return None
            return data

        def _destination_dir() -> Path:
            dest = dest_edit.text().strip()
            if dest:
                return Path(dest)
            media = media_edit.text().strip()
            return Path(media).parent if media else Path.home()

        def on_extract_srt() -> None:
            selected = _selected_track()
            if selected is None:
                return
            kind, index = selected
            if kind != "subtitle":
                QMessageBox.information(
                    widget,
                    "Piste non adaptée",
                    "Choisissez une piste de sous-titres dans la liste pour l'extraire en .srt.",
                )
                return
            media = media_edit.text().strip()
            srt_btn.setEnabled(False)
            status_lbl.setText("Extraction des sous-titres en cours…")

            def job(_report: Callable[[str], None]) -> Any:
                return extract_subtitle_track(media, index, _destination_dir())

            def done(kind2: str, payload: Any) -> None:
                srt_btn.setEnabled(True)
                if kind2 == "error":
                    status_lbl.setText("Extraction impossible.")
                    _report_error(payload)
                    return
                status_lbl.setText(f"✅ Sous-titres extraits : {payload}")
                output_edit.appendPlainText(f"\n✅ Sous-titres extraits vers :\n{payload}")

            _launch_job(job, done)

        def on_extract_wav() -> None:
            selected = _selected_track()
            if selected is None:
                return
            kind, index = selected
            if kind != "audio":
                QMessageBox.information(
                    widget,
                    "Piste non adaptée",
                    "Choisissez une piste audio dans la liste pour l'extraire en .wav.",
                )
                return
            media = media_edit.text().strip()
            wav_btn.setEnabled(False)
            status_lbl.setText("Extraction de l'audio en cours…")

            def job(_report: Callable[[str], None]) -> Any:
                return extract_audio_track(media, index, _destination_dir())

            def done(kind2: str, payload: Any) -> None:
                wav_btn.setEnabled(True)
                if kind2 == "error":
                    status_lbl.setText("Extraction impossible.")
                    _report_error(payload)
                    return
                status_lbl.setText(f"✅ Audio extrait : {payload}")
                output_edit.appendPlainText(f"\n✅ Piste audio extraite vers :\n{payload}")

            _launch_job(job, done)

        def on_create_template() -> None:
            media = media_edit.text().strip()
            base = Path(media).stem if media else "sous-titres"
            dest_dir = _destination_dir()
            title = base

            def job(_report: Callable[[str], None]) -> Any:
                return create_srt_template(dest_dir / f"{base} - modele.srt", title=title)

            def done(kind: str, payload: Any) -> None:
                if kind == "error":
                    _report_error(payload)
                    return
                status_lbl.setText(f"✅ Modèle créé : {payload}")
                output_edit.appendPlainText(
                    f"\n✅ Modèle de sous-titres créé :\n{payload}\n"
                    "Complétez-le dans un éditeur de texte (encodage UTF-8)."
                )

            _launch_job(job, done)

        browse_media_btn.clicked.connect(on_browse_media)
        browse_dest_btn.clicked.connect(
            lambda: dest_edit.setText(
                QFileDialog.getExistingDirectory(widget, "Dossier des extraits", dest_edit.text())
                or dest_edit.text()
            )
        )
        list_btn.clicked.connect(on_list)
        srt_btn.clicked.connect(on_extract_srt)
        wav_btn.clicked.connect(on_extract_wav)
        template_btn.clicked.connect(on_create_template)
        return page

    # ------------------------------------------------------------------
    # 5. Inventaire & export CSV
    # ------------------------------------------------------------------
    def build_inventory_page() -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)
        layout.setSpacing(10)

        top_card = _card()
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(12, 10, 12, 10)
        folder_row = QHBoxLayout()
        folder_edit = QLineEdit()
        folder_edit.setObjectName("creatorsInventoryFolder")
        folder_edit.setPlaceholderText(
            "Dossier du projet (ou tout dossier de médias) à inventorier…"
        )
        browse_btn = QPushButton("📂 Parcourir…")
        scan_btn = QPushButton("📋 Analyser")
        scan_btn.setObjectName("creatorsInventoryScan")
        folder_row.addWidget(folder_edit, stretch=1)
        folder_row.addWidget(browse_btn)
        folder_row.addWidget(scan_btn)
        top_layout.addLayout(folder_row)
        options_row = QHBoxLayout()
        recursive_chk = QCheckBox("Inclure les sous-dossiers")
        recursive_chk.setObjectName("creatorsInventoryRecursive")
        recursive_chk.setChecked(True)
        sources_chk = QCheckBox(
            "Ajouter les adresses source de l'historique des téléchargements"
        )
        sources_chk.setObjectName("creatorsInventorySources")
        sources_chk.setChecked(history is not None)
        sources_chk.setVisible(history is not None)
        options_row.addWidget(recursive_chk)
        options_row.addWidget(sources_chk)
        options_row.addStretch()
        top_layout.addLayout(options_row)
        layout.addWidget(top_card)

        summary_lbl = QLabel(
            "L'inventaire relève, pour chaque média : source, conteneur, codecs, résolution, "
            "FPS, durée, pistes et taille. Exportable en CSV pour Excel."
        )
        summary_lbl.setObjectName("mutedLabel")
        summary_lbl.setWordWrap(True)
        layout.addWidget(summary_lbl)

        table = QTableWidget(0, 10)
        table.setObjectName("creatorsInventoryTable")
        table.setHorizontalHeaderLabels(
            [
                "Fichier", "Type", "Taille", "Durée", "Conteneur",
                "Vidéo", "Audio", "Résolution", "FPS", "Source",
            ]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table, stretch=1)

        bottom_row = QHBoxLayout()
        export_btn = QPushButton("💾 Exporter en CSV…")
        export_btn.setObjectName("creatorsInventoryExport")
        export_btn.setEnabled(False)
        open_export_btn = QPushButton("📁 Ouvrir le dossier de l'export")
        open_export_btn.setObjectName("creatorsInventoryOpenExport")
        open_export_btn.setEnabled(False)
        bottom_row.addWidget(export_btn)
        bottom_row.addWidget(open_export_btn)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        state: dict[str, Any] = {"rows": [], "last_export": None}

        def on_scan() -> None:
            folder = folder_edit.text().strip()
            if not folder:
                QMessageBox.warning(
                    widget, "Dossier manquant", "Choisissez un dossier à inventorier."
                )
                return
            scan_btn.setEnabled(False)
            export_btn.setEnabled(False)
            summary_lbl.setText("Analyse en cours…")

            sources = _download_sources() if sources_chk.isChecked() else {}

            def job(report: Callable[[str], None]) -> Any:
                return scan_tree(
                    folder,
                    recursive=recursive_chk.isChecked(),
                    sources=sources,
                    progress=lambda done, total, name: report(f"Analyse {done}/{total} — {name}"),
                )

            def done(kind: str, payload: Any) -> None:
                scan_btn.setEnabled(True)
                if kind == "error":
                    summary_lbl.setText("Analyse impossible.")
                    _safe(lambda: (_ for _ in ()).throw(payload))
                    return
                rows = payload
                state["rows"] = rows
                table.setRowCount(len(rows))
                for row_index, row in enumerate(rows):
                    values = [
                        row.path.name,
                        row.kind.label,
                        format_bytes(row.size_bytes),
                        row.duration_human(),
                        row.container,
                        row.video_codec,
                        row.audio_codec,
                        row.resolution,
                        f"{row.fps:.2f}".replace(".", ",") if row.fps else "",
                        row.source,
                    ]
                    for col, value in enumerate(values):
                        table.setItem(row_index, col, QTableWidgetItem(value))
                total_size = sum(r.size_bytes for r in rows)
                by_kind: dict[str, int] = {}
                for row in rows:
                    by_kind[row.kind.label] = by_kind.get(row.kind.label, 0) + 1
                kind_txt = " · ".join(
                    f"{v} {k.lower()}" for k, v in sorted(by_kind.items())
                )
                summary_lbl.setText(
                    f"{len(rows)} média(s) inventorié(s) ({kind_txt}) — {format_bytes(total_size)} "
                    "au total. Aucun fichier n'a été modifié."
                )
                export_btn.setEnabled(bool(rows))

            _launch_job(job, done, on_progress=lambda msg: summary_lbl.setText(msg))

        def on_export() -> None:
            if not state["rows"]:
                return
            suggested = Path(folder_edit.text().strip() or Path.home()) / "inventaire-overload.csv"
            chosen, _ = QFileDialog.getSaveFileName(
                widget, "Exporter l'inventaire", str(suggested), "CSV (*.csv)"
            )
            if not chosen:
                return

            def job(_report: Callable[[str], None]) -> Any:
                return export_inventory_csv(state["rows"], chosen)

            def done(kind: str, payload: Any) -> None:
                if kind == "error":
                    summary_lbl.setText("Export impossible.")
                    _report_error(payload)
                    return
                state["last_export"] = payload
                summary_lbl.setText(f"✅ Inventaire exporté : {payload}")
                open_export_btn.setEnabled(True)

            _launch_job(job, done)

        browse_btn.clicked.connect(
            lambda: folder_edit.setText(
                QFileDialog.getExistingDirectory(
                    widget, "Dossier à inventorier", folder_edit.text()
                )
                or folder_edit.text()
            )
        )
        def on_open_export() -> None:
            if state["last_export"] is not None:
                _safe(lambda: open_folder(state["last_export"]))

        scan_btn.clicked.connect(on_scan)
        export_btn.clicked.connect(on_export)
        open_export_btn.clicked.connect(on_open_export)
        return page

    # ------------------------------------------------------------------
    # 6. Profils de montage
    # ------------------------------------------------------------------
    def build_profiles_page() -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(4, 6, 4, 4)
        outer.setSpacing(10)

        list_card = _card()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 10, 12, 10)
        list_title = QLabel("🎚 Profils dédiés aux logiciels de montage")
        list_title.setObjectName("sectionTitle")
        list_layout.addWidget(list_title)
        list_note = QLabel(
            "Chaque profil définit la structure de dossiers du projet et les formats "
            "recommandés à l'importation. Les profils intégrés sont fournis par OverLoad ; "
            "vos profils personnalisés sont enregistrés dans vos données locales."
        )
        list_note.setObjectName("mutedLabel")
        list_note.setWordWrap(True)
        list_layout.addWidget(list_note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        profiles_layout = QVBoxLayout(container)
        profiles_layout.setContentsMargins(0, 0, 4, 0)
        profiles_layout.setSpacing(8)
        profiles_layout.addStretch()
        scroll.setWidget(container)
        list_layout.addWidget(scroll, stretch=1)
        outer.addWidget(list_card, stretch=3)

        form_card = _card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_title = QLabel("➕ Créer un profil personnalisé")
        form_title.setObjectName("sectionTitle")
        form_layout.addWidget(form_title)

        name_edit = QLineEdit()
        name_edit.setObjectName("creatorsProfileName")
        name_edit.setPlaceholderText("Nom du profil (ex. Montage YouTube 4K)")
        form_layout.addWidget(name_edit)

        folder_fields: dict[str, QLineEdit] = {}
        for key, label, default in [
            ("video_folder", "Dossier vidéos :", "01_Videos"),
            ("audio_folder", "Dossier audio :", "02_Audio"),
            ("image_folder", "Dossier images :", "03_Images"),
            ("subtitle_folder", "Dossier sous-titres :", "04_Sous-titres"),
            ("project_folder", "Dossier projets du monteur :", "05_Projets"),
            ("export_folder", "Dossier exports :", "06_Exports"),
        ]:
            row = QHBoxLayout()
            field = QLineEdit()
            field.setText(default)
            field.setObjectName(f"creatorsProfile_{key}")
            folder_fields[key] = field
            row.addWidget(QLabel(label))
            row.addWidget(field, stretch=1)
            form_layout.addLayout(row)

        extra_edit = QLineEdit()
        extra_edit.setObjectName("creatorsProfileExtra")
        extra_edit.setPlaceholderText("Dossiers supplémentaires séparés par « ; » (optionnel)")
        form_layout.addWidget(extra_edit)

        container_edit = QLineEdit()
        container_edit.setObjectName("creatorsProfileContainer")
        container_edit.setPlaceholderText("Conteneurs recommandés (ex. MP4 / MOV)")
        video_fmt_edit = QLineEdit()
        video_fmt_edit.setObjectName("creatorsProfileVideoFmt")
        video_fmt_edit.setPlaceholderText(
            "Codecs vidéo recommandés (ex. ProRes 422, H.264 8 bits)"
        )
        audio_fmt_edit = QLineEdit()
        audio_fmt_edit.setObjectName("creatorsProfileAudioFmt")
        audio_fmt_edit.setPlaceholderText("Audio recommandé (ex. PCM 48 kHz)")
        form_layout.addWidget(container_edit)
        form_layout.addWidget(video_fmt_edit)
        form_layout.addWidget(audio_fmt_edit)

        notes_edit = QLineEdit()
        notes_edit.setObjectName("creatorsProfileNotes")
        notes_edit.setPlaceholderText("Conseils / remarques (optionnel)")
        form_layout.addWidget(notes_edit)

        save_btn = QPushButton("💾 Enregistrer le profil")
        save_btn.setObjectName("creatorsProfileSave")
        form_layout.addWidget(save_btn)
        form_layout.addStretch()
        outer.addWidget(form_card, stretch=2)

        state = {"cards": []}

        def refresh() -> None:
            for card in state["cards"]:
                card.deleteLater()
            state["cards"] = []
            while profiles_layout.count() > 1:
                item = profiles_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for profile in workspace.profiles.list_profiles():
                card = QFrame()
                card.setObjectName("itemCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 8, 12, 8)
                head = QHBoxLayout()
                name_lbl = QLabel(profile.name)
                name_lbl.setStyleSheet("font-weight: 700;")
                badge = QLabel("Intégré" if profile.builtin else "Personnalisé")
                badge.setObjectName("mutedLabel")
                head.addWidget(name_lbl)
                head.addStretch()
                head.addWidget(badge)
                if not profile.builtin:
                    delete_btn = QPushButton("🗑")
                    delete_btn.setFixedWidth(36)
                    delete_btn.clicked.connect(
                        lambda _checked=False, pid=profile.id: _remove_profile(pid)
                    )
                    head.addWidget(delete_btn)
                card_layout.addLayout(head)
                if profile.description:
                    desc = QLabel(profile.description)
                    desc.setObjectName("mutedLabel")
                    desc.setWordWrap(True)
                    card_layout.addWidget(desc)
                folders_lbl = QLabel("Structure : " + " / ".join(profile.folders()))
                folders_lbl.setWordWrap(True)
                card_layout.addWidget(folders_lbl)
                recommended = " · ".join(
                    part
                    for part in (
                        profile.recommended_container,
                        profile.recommended_video,
                        profile.recommended_audio,
                    )
                    if part
                )
                formats = QLabel("Formats conseillés : " + (recommended or "—"))
                formats.setWordWrap(True)
                card_layout.addWidget(formats)
                if profile.notes:
                    notes = QLabel(f"💡 {profile.notes}")
                    notes.setWordWrap(True)
                    notes.setObjectName("mutedLabel")
                    card_layout.addWidget(notes)
                profiles_layout.insertWidget(profiles_layout.count() - 1, card)
                state["cards"].append(card)

        def _remove_profile(profile_id: str) -> None:
            answer = QMessageBox.question(
                widget,
                "Supprimer ce profil ?",
                "Supprimer ce profil personnalisé ?\n\n"
                "Les projets déjà créés avec ce profil conservent leurs dossiers : rien n'est "
                "supprimé sur le disque.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                _safe(lambda: workspace.profiles.remove_custom(profile_id))
                refresh()

        def on_save() -> None:
            extra = [part.strip() for part in extra_edit.text().split(";") if part.strip()]
            profile = _safe(
                lambda: workspace.profiles.add_custom(
                    name=name_edit.text(),
                    video_folder=folder_fields["video_folder"].text(),
                    audio_folder=folder_fields["audio_folder"].text(),
                    image_folder=folder_fields["image_folder"].text(),
                    subtitle_folder=folder_fields["subtitle_folder"].text(),
                    project_folder=folder_fields["project_folder"].text(),
                    export_folder=folder_fields["export_folder"].text(),
                    extra_folders=extra,
                    recommended_container=container_edit.text(),
                    recommended_video=video_fmt_edit.text(),
                    recommended_audio=audio_fmt_edit.text(),
                    notes=notes_edit.text(),
                )
            )
            if profile is None:
                return
            QMessageBox.information(
                widget,
                "Profil enregistré",
                f"Le profil « {profile.name} » est disponible dans « Mes projets » et "
                "« Préparer mon projet ».",
            )
            name_edit.clear()
            extra_edit.clear()
            container_edit.clear()
            video_fmt_edit.clear()
            audio_fmt_edit.clear()
            notes_edit.clear()
            refresh()

        save_btn.clicked.connect(on_save)
        refresh()
        page_refreshers[5] = refresh
        return page

    page_refreshers: dict[int, Callable[[], None]] = {}

    tabs.addTab(build_projects_page(), "🗂 Mes projets")
    tabs.addTab(build_prepare_page(), "📥 Préparer mon projet")
    tabs.addTab(build_rename_page(), "✏️ Renommer par lots")
    tabs.addTab(build_tracks_page(), "💬 Sous-titres & pistes")
    tabs.addTab(build_inventory_page(), "📋 Inventaire & export")
    tabs.addTab(build_profiles_page(), "🎚 Profils de montage")

    def _on_tab_changed(index: int) -> None:
        refresher = page_refreshers.get(index)
        if refresher is not None:
            refresher()

    tabs.currentChanged.connect(_on_tab_changed)
    return widget
