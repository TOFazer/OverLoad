# Licences des composants tiers

Chaque dépendance distribuée avec **OverLoad** (en particulier dans `OverLoad.exe` et l'archive portable Windows) est listée ci-dessous avec sa licence applicable.

| Composant | Rôle | Licence | Statut |
|---|---|---|---|
| **PySide6-Essentials** (Qt for Python — `QtCore`, `QtGui`, `QtWidgets`) | Interface graphique native Windows embarquée dans l'application | **LGPL v3** | **Intégré** (`pyproject.toml`, livré en bibliothèques dynamiques dans l'édition portable) |
| **PyInstaller** (bootloader d'exécution) | Empaquetage de `OverLoad.exe` | **GPL v2+** avec **exception « bootloader »** + **Apache-2.0** (hooks runtime) | **Intégré** (`scripts/build_windows.py`) |
| **FFmpeg / ffprobe** (build LGPL, sans `--enable-gpl` ni `--enable-nonfree`) | Analyse locale et vérification de lecture | LGPL v2.1+ | Intégré (outils séparés embarqués, build BtbN LGPL) |
| **Inno Setup** | Installateur Windows (`OverLoad-Setup.exe`) | Licence Inno Setup | Script prêt (`packaging/OverLoad.iss`) |

yt-dlp n'est pas intégré dans la version 1 (voir `docs/audit/PHASE0_AUDIT.md`, décision 2).

## Obligations LGPL v3 (PySide6 / Qt)

- `PySide6-Essentials` est utilisé sans aucune modification du code source de Qt.
- L'archive portable `OverLoad-Portable-win64.zip` conserve les bibliothèques dynamiques Qt dans `_internal/PySide6/`, permettant à tout utilisateur final de les inspecter ou de les remplacer par une version compatible.
- Le texte complet des licences est joint dans le dossier de distribution (`LICENSE` et `THIRD_PARTY_LICENSES.md`).

## PyInstaller : exception « bootloader » (vérifiée)

Source : fichier `COPYING.txt` du dépôt officiel `pyinstaller/pyinstaller`, consulté le 2026-10-09.

- PyInstaller est sous GPL v2 (ou ultérieure).
- L'exception accorde une permission illimitée d'intégrer le bootloader compilé et les fichiers associés (`bootloader/`, `PyInstaller/loader`) dans des combinaisons avec d'autres programmes, et de distribuer ces combinaisons sans restriction liée à ces fichiers.
- Les **restrictions GPL restent applicables** à la modification des fichiers de PyInstaller et à la distribution hors d'un exécutable combiné.
- Les hooks d'exécution (`PyInstaller/hooks/rthooks`) et les modules fournis à l'exécution (`pyi_splash`, `_pyi_rth_utils`) sont sous Apache 2.0.

## FFmpeg / FFprobe

- Distribution non modifiée du build **win64-lgpl** de
  [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest).
  Aucun build GPL ou nonfree n'est sélectionné par le script.
- Le script `scripts/prepare_ffmpeg.py` conserve les notices et la documentation
  de l'archive dans `tools/`, embarquées avec les exécutables.
- Sources FFmpeg : https://github.com/FFmpeg/FFmpeg ; recettes et dépendances du build :
  https://github.com/BtbN/FFmpeg-Builds. Les conditions des composants de ce build
  restent applicables ; consulter ses notices pour leur détail.
- Ces outils sont lancés comme processus distincts, jamais liés au code Python.
  Dans l'édition portable ils se trouvent sous `_internal/tools/` et peuvent être
  remplacés par des versions compatibles. Dans l'édition autonome ils sont extraits
  au lancement par PyInstaller.
