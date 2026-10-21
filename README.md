# OverLoad

⚡ **OverLoad** — Organise et prépare tes médias.

🎬 Télécharge des fichiers depuis des adresses directes prises en charge, retrouve tes vidéos, musiques et images, analyse-les et convertis-les, sans installer de dépendances.

**Sources prises en charge (version 1) :** adresses HTTP(S) qui pointent directement vers un fichier. OverLoad ne contourne ni les protections d'accès, ni les DRM, ni les restrictions d'une plateforme.

**OverLoad — Your media, your way.**

---

## ✨ Nouveauté — Bibliothèque multimédia intégrée (v0.2)

OverLoad embarque désormais une **bibliothèque multimédia** pour retrouver un fichier en quelques secondes, même plusieurs mois après son téléchargement.

- **Vignettes** : grille d'aperçus pour vidéos, musiques et images (miniatures générées en cache, placeholder coloré si FFmpeg/Pillow indisponibles).
- **Recherche & filtres** : par nom/chemin, type (vidéo/audio/image/autre), taille, date (aujourd'hui, 7 jours, 3 mois…), durée et extension. Tri par date, taille ou nom.
- **Doublons** : détection par empreinte SHA-256 (ou hash partiel rapide) — groupement et affichage du gaspillage d'espace, **sans suppression automatique**.
- **Classement automatique** : règle de dossiers personnalisables par type + sous-dossiers par date (`%Y/%m`, `%Y-%m`…) et surcharges par extension. Aperçu avant enregistrement. Jamais d'écrasement : ` (2)`, ` (3)`…
- **Prévisualisation & ouverture** : double-clic → aperçu (vignette + métadonnées), boutons *Ouvrir* (lecteur par défaut) et *Ouvrir l'emplacement* (Explorer / Finder / dossier parent).
- **Le plus** : barre de recherche + filtre de date large = retrouver un fichier d'il y a 4 mois en tapant 3 lettres. Index SQLite persistant dans `%APPDATA%\OverLoad\library.db`.

> Exemple : tapez `vacances` + filtre *3 derniers mois* → tous les `vacances_2024_*.mp4` d'août apparaissent, triés par récence, avec leur taille et durée.

Captures (grille, filtre doublons, classement auto) : voir `docs/BIBLIOTHEQUE.md`.

---

## Développement

- Audit initial, licences et architecture cible : [`docs/audit/PHASE0_AUDIT.md`](docs/audit/PHASE0_AUDIT.md)
- Bibliothèque : [`docs/BIBLIOTHEQUE.md`](docs/BIBLIOTHEQUE.md)
- Composants tiers et licences : [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)
- Licence du projet : [MIT](LICENSE)

Lancer les tests (Python 3.11 ou plus) :

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest
```

Lancer l'interface (Windows / Linux / macOS, nécessite PySide6) :

```bash
python -m pip install -e ".[gui]"
python -m overload
# ou
overload
```

Pour la version 1, seules les adresses HTTP(S) qui pointent directement vers un fichier sont acceptées. Les adresses locales ou privées (localhost, 192.168.x.x, etc.) sont refusées, y compris lorsqu'un nom de domaine y redirige.

---

## 📦 Application Windows (.exe)

OverLoad est distribué en **exécutable portable** et **installateur** pour Windows 11 64-bit.

### Build local (Windows)

```powershell
pip install -e ".[build]"
pyinstaller overload.spec --noconfirm --clean
# -> dist/OverLoad.exe (~90 Mo)
# Installateur (optionnel) : ouvrir installer/OverLoad.iss avec Inno Setup 6
```

Scripts :

- `scripts/build_exe.ps1` — build complet Windows (PyInstaller + Inno Setup si présent)
- `scripts/build_exe.sh` — vérification Linux/macOS (tests + imports)

CI : `.github/workflows/build.yml` génère `OverLoad.exe` à chaque push sur `windows-latest` et publie l'artefact.

Portable : si un dossier `OverLoad-data` existe à côté de `OverLoad.exe`, les données (base, vignettes, paramètres) y sont stockées. Sinon : `%APPDATA%\OverLoad`.

### Données utilisateur

| Donnée | Emplacement stable |
|---|---|
| Bibliothèque | `%APPDATA%\OverLoad\library.db` (SQLite) |
| Vignettes | `%APPDATA%\OverLoad\thumbnails\` |
| Paramètres | `%APPDATA%\OverLoad\settings.json` |
| Logs | `%APPDATA%\OverLoad\logs\` |

Canaux : `OverLoad` (stable), `OverLoad-Beta` et `OverLoad-Dev` ont des dossiers séparés pour éviter toute perte de données.
