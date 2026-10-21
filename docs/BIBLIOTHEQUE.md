# Bibliothèque multimédia intégrée — documentation

> Fonction 2 du cahier des charges : *Une bibliothèque multimédia intégrée*.

## Objectif

Permettre à l'utilisateur de **retrouver en quelques secondes un fichier téléchargé il y a plusieurs mois**, sans fouiller l'explorateur.

## Fonctionnalités

### 1. Vignettes en grille

- Affichage en `QListWidget` mode icônes (220×200 par carte).
- Pour chaque fichier : miniature (cache `thumbnails/`), nom, taille humaine, date, badge type et durée si disponible.
- Génération :
  - Images → Pillow (resize 320×180, cache invalidé si `mtime` change).
  - Vidéos → `ffmpeg -ss 1 -i input -frames:v 1 -vf scale=320:-1` si FFmpeg présent, sinon placeholder couleur.
  - Audios/Autres → placeholder coloré (bleu vidéo, vert audio, orange image, gris autre).
- Double-clic → dialogue de prévisualisation avec vignette agrandie et métadonnées.

### 2. Recherche & filtres

Barre toujours visible :

- **Recherche texte** : `LIKE %query%` insensible à la casse sur `filename` et `path` (SQLite). Idéal pour taper `vacances` et retrouver `vacances_aout_2024.mp4`.
- **Type** : vidéo / audio / image / autre (déduit de l'extension + `mimetypes`).
- **Taille** : >100 Mo, >1 Go, <10 Mo… (filtre `size`).
- **Date** : aujourd'hui, 7 jours, 30 jours, 90 jours, année, >1 an (filtre `mtime`).
- **Durée** : <1 min, 1–5 min, 5–30 min, >30 min (filtre `duration`, si `ffprobe` a pu l'extraire).
- **Tri** : plus récents (`mtime DESC`), plus volumineux (`size DESC`), nom, durée.
- **Pagination** : 500 vignettes max affichées, message si plus de résultats → incite à affiner.

API :

```python
from overload.library.db import LibraryStore
from overload.library.filters import FilterCriteria
from datetime import datetime, timedelta

store = LibraryStore("library.db")
# Retrouver un fichier de 4 mois :
crit = FilterCriteria(query="vacances", after=datetime.now() - timedelta(days=120))
results = store.search(**crit.normalized())
```

### 3. Doublons

- Empreinte complète SHA-256 (`file_hash`) + hash partiel rapide (BLAKE2b 1 Mio + taille) pour pré-trier sans lire tout le fichier.
- `find_duplicates(entries)` : groupe par hash, tri par `wasted_bytes` décroissant.
- `find_duplicates_in_store(store, compute_missing_hash=True)` : calcule les hash manquants pour les groupes de même taille.
- **Jamais de suppression automatique** : l'UI affiche les groupes avec leur gaspillage, propose *Ouvrir* / *Ouvrir l'emplacement* et laisse l'utilisateur décider.
- Badge *Doublons* dans la barre de filtres pour n'afficher que les fichiers en double.

### 4. Classement automatique

Configuration `OrganizerConfig` (persistée dans `settings.json`) :

```json
{
  "enabled": true,
  "base_directory": "D:/Médias/OverLoad",
  "folders": {"video": "Vidéos", "audio": "Musiques", "image": "Images", "other": "Autres"},
  "date_template": "%Y/%m",
  "extension_overrides": {".mp3": "Musiques/Podcasts"}
}
```

- `classify_entry(entry, config)` → chemin relatif `Vidéos/2024/10`.
- `destination_for(entry, config, root)` → chemin complet avec `sanitize_filename`.
- `organize_file(source, config, move=True)` → crée les dossiers, garantit l'unicité (` (2)`), déplace ou copie.
- Aperçu dans les paramètres : 3 exemples (vidéo/audio/image) → destination prévue.
- Intégré au téléchargement : si activé, chaque `download_to` réussi est immédiatement classé puis réindexé.

### 5. Prévisualisation & emplacement

```python
from overload.library.preview import open_media, reveal_in_explorer, preview_info

open_media(Path("video.mp4"))          # os.startfile / open / xdg-open
reveal_in_explorer(Path("video.mp4"))  # explorer /select, / open -R / xdg-open dossier
preview_info(Path("photo.jpg"))        # dict pour la prévisualisation rapide
```

Gestion d'erreur : `OverloadError` si fichier déplacé/supprimé, message clair et action suggérée.

## Persistance

- **SQLite** `library.db` : table `media_entries` + index sur `media_type`, `size`, `mtime`, `hash`, `filename`.
- Schéma versionné (`PRAGMA user_version`), migration douce.
- `LibraryStore` : `upsert_entry`, `search`, `remove_missing`, `stats`.
- `scan_directory(root, recursive=True)` : ignore `.part`, `Thumbs.db` etc., probe optionnel `ffprobe`/`Pillow`.

## Le plus — retrouver un fichier de plusieurs mois

Scénario type :

1. Utilisateur a téléchargé `anniversaire_2024.mp4` le 15 juin (4 mois plus tôt).
2. Il tape `anniv` dans la recherche.
3. Ajoute le filtre *3 derniers mois* → *Ce mois-ci* ne le trouve pas, il élargit à *Cette année* et le fichier apparaît en haut (tri *Plus récents*).
4. Double-clic → aperçu avec vignette, taille, date, durée, bouton *Ouvrir l'emplacement*.

Grâce à l'index SQLite et aux filtres combinés, même 5 000 fichiers restent fluides.

## Tests

- `tests/unit/test_library_*.py` : 70+ tests (modèles, DB, scanner, doublons, organizer, filtres, thumbnails, preview).
- `pytest` : 112 tests passants (dont anciens tests téléchargement).

## Limites assumées

- Pas de lecture vidéo intégrée : délégation au lecteur système (VLC, Films & TV…) pour éviter d'embarquer FFmpeg GPL.
- Vignettes vidéo nécessitent FFmpeg en PATH, sinon placeholder — l'indexation ne bloque jamais.
- Durée nécessite `ffprobe`, sinon `None` — les filtres durée ignorent alors ces fichiers.
- Pas de FTS5 pour l'instant : `LIKE %query%` suffit jusqu'à ~10k fichiers (benchmark à faire en Phase 9 si besoin FTS).

## Évolutions prévues (Phase 9)

- Recherche avancée FTS5, tags et collections virtuelles.
- Prévisualisation audio avec waveform.
- Règles de classement par taille/durée et par source.
