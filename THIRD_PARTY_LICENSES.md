# Licences des composants tiers

## Composants embarqués (v0.2)

| Composant | Rôle | Licence | Version testée |
|---|---|---|---|
| Pillow | Miniatures d'images et placeholders | MIT (HPND pour certaines parties) | 10+ |
| FFmpeg / ffprobe (build LGPL, sans `--enable-gpl` ni `--enable-nonfree`) | Miniatures vidéo et durée (optionnel, non embarqué par défaut) | LGPL v2.1+ | 6+ |
| PySide6 (Qt for Python) | Interface | LGPL v3 | 6.6+ |
| PyInstaller | Génération de l'exécutable | GPL v2 (ou ultérieure) avec exception « bootloader » | 6+ |
| Inno Setup | Installateur | Licence Inno Setup | 6 |

`yt-dlp` n'est pas intégré dans la version 1 (voir `docs/audit/PHASE0_AUDIT.md`, décision 2).

Composants de build/dev (non distribués) : `pytest` (MIT), `ruff` (MIT).

## Détails LGPL

- **FFmpeg LGPL** : distribué en binaire séparé (non lié statiquement), avec mention de licence et sources disponibles sur demande. Vérifier à chaque release : `ffmpeg -version` et `-buildconf` ne doivent pas contenir `--enable-gpl`.
- **PySide6 LGPL v3** : l'utilisateur peut remplacer la bibliothèque (PySide6 reste un import dynamique). Mention de licence dans l'installateur.

## PyInstaller : exception « bootloader » (vérifiée)

Source : fichier `COPYING.txt` du dépôt officiel `pyinstaller/pyinstaller`, consulté le 2026-10-09.

- PyInstaller est sous GPL v2 (ou ultérieure).
- L'exception accorde une permission illimitée d'intégrer le bootloader compilé et les fichiers associés (`bootloader/`, `PyInstaller/loader`) dans des combinaisons avec d'autres programmes, et de distribuer ces combinaisons sans restriction liée à ces fichiers.
- Les **restrictions GPL restent applicables** à la modification des fichiers de PyInstaller et à la distribution hors d'un exécutable combiné.
- Les hooks d'exécution (`PyInstaller/hooks/rthooks`) et les modules fournis à l'exécution (`pyi_splash`, `_pyi_rth_utils`) sont sous Apache 2.0.

Conséquence pratique : un exécutable OverLoad produit par PyInstaller peut être distribué sous MIT. Il faut en revanche joindre le texte des licences des composants embarqués et ne pas modifier PyInstaller sans respecter la GPL. Cette lecture reste à faire valider par un juriste avant la première diffusion publique.
