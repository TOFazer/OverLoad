# Licences des composants tiers

Dépendances d'exécution actuelles : **PySide6** (Qt for Python) et ses bibliothèques Qt, embarquées
dans `OverLoad.exe` par PyInstaller. Le moteur de téléchargement n'utilise que la bibliothèque
standard Python.

Composants prévus, à ajouter ici avant leur intégration :

| Composant | Rôle | Licence | Statut |
|---|---|---|---|
| FFmpeg / ffprobe (build LGPL, sans `--enable-gpl` ni `--enable-nonfree`) | Analyse et conversion | LGPL v2.1+ | Prévu (Phase 5) |
| PySide6 / Qt 6 | Interface de bureau (embarqué dans OverLoad.exe) | LGPL v3 (Qt sous LGPL ; vérifier les notices du paquet installé) | **Utilisé** depuis la Phase 2 |
| PyInstaller | Génération de l'exécutable (outil de build, non embarqué hors bootloader) | GPL v2 (ou ultérieure) avec exception « bootloader » | **Utilisé** au build — exception vérifiée, voir ci-dessous |
| Inno Setup | Installateur | Licence Inno Setup | Prévu |

yt-dlp n'est pas intégré dans la version 1 (voir `docs/audit/PHASE0_AUDIT.md`, décision 2).

## PyInstaller : exception « bootloader » (vérifiée)

Source : fichier `COPYING.txt` du dépôt officiel `pyinstaller/pyinstaller`, consulté le 2026-10-09.

- PyInstaller est sous GPL v2 (ou ultérieure).
- L'exception accorde une permission illimitée d'intégrer le bootloader compilé et les fichiers
  associés (`bootloader/`, `PyInstaller/loader`) dans des combinaisons avec d'autres programmes, et
de distribuer ces combinaisons sans restriction liée à ces fichiers.
- Les **restrictions GPL restent applicables** à la modification des fichiers de PyInstaller et à la
distribution hors d'un exécutable combiné.
- Les hooks d'exécution (`PyInstaller/hooks/rthooks`) et les modules fournis à l'exécution
  (`pyi_splash`, `_pyi_rth_utils`) sont sous Apache 2.0.

Conséquence pratique : un exécutable OverLoad produit par PyInstaller peut être distribué sous MIT.
Il faut en revanche joindre le texte des licences des composants embarqués et ne pas modifier
PyInstaller sans respecter la GPL. Cette lecture reste à faire valider par un juriste avant la
première diffusion publique.
