# Licences des composants tiers

OverLoad n'embarque actuellement aucune dépendance d'exécution (bibliothèque standard Python uniquement).

Composants prévus, à ajouter ici avant leur intégration :

| Composant | Rôle | Licence | Statut |
|---|---|---|---|
| FFmpeg / ffprobe (build LGPL, sans `--enable-gpl` ni `--enable-nonfree`) | Analyse et conversion | LGPL v2.1+ | Prévu (Phase 5) |
| PySide6 (Qt for Python) | Interface | LGPL v3 | Prévu (Phase 2) |
| PyInstaller | Génération de l'exécutable | GPL v2 avec exception bootloader | Prévu (Phase 2), à confirmer |
| Inno Setup | Installateur | Licence Inno Setup | Prévu (Phase 2) |

yt-dlp n'est pas intégré dans la version 1 (voir `docs/audit/PHASE0_AUDIT.md`, décision 2).
