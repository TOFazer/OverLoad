# OverLoad

⚡ **OverLoad** — Organise et prépare tes médias.

🎬 Télécharge des fichiers depuis des adresses directes prises en charge, retrouve tes vidéos, musiques et images, analyse-les, prépare tes projets de montage et organise tes médias, directement dans une **application native Windows (`OverLoad.exe`)** sans dépendance à installer.

**Sources prises en charge (version 1) :** adresses HTTP(S) qui pointent directement vers un fichier. OverLoad ne contourne ni les protections d'accès, ni les DRM, ni les restrictions d'une plateforme.

**OverLoad — Your media, your way.**

---

## Une interface repensée (v1.1)

![Accueil d'OverLoad](docs/design/accueil.png)

La version 1.1 introduit une interface entièrement redessinée pour
`OverLoad.exe` :

- **Thème sombre premium par défaut** (fond `#111318`, cartes `#1B1E27`, accent
  violet `#8B5CF6`), **thème clair** complet et **six couleurs d'accent**
  commutables en un clic, sans redémarrage.
- **Navigation latérale** : Accueil, Téléchargements, Créateurs, Analyse
  multimédia et Paramètres ; logo et nom OverLoad toujours visibles ; barre
  supérieure avec recherche globale, raccourci de téléchargement et accès
  rapide aux réglages.
- **Accueil actionnable** : champ de lien central collable (Ctrl+V) avec
  validation en direct, gros bouton **Télécharger**, dossier de destination
  modifiable, indicateurs de débit / file / terminés / espace disque et
  téléchargements récents avec vraies vignettes.
- **Cartes de téléchargement lisibles** : vignette ou icône de format, nom,
  hôte, badge d'état coloré, grande barre de progression animée, pourcentage,
  taille, vitesse, temps restant et actions Pause / Reprendre / Relancer /
  Annuler / Ouvrir / Retirer.
- **Historique consultable** : filtres avec compteurs, présence réelle du
  fichier vérifiée sur le disque, recherche instantanée.
- **Messages d'erreur compréhensibles** : plus de « Échec » vague — cause
  probable, explication et action recommandée en français, détail technique
  disponible sur demande.
- **Personnalisation** : thème sombre/clair, couleur d'accent, taille
  d'interface (Compact / Normal / Grand), mémorisés dans `settings.json`.
- **Interface adaptative** : la barre latérale se replie en rail d'icônes et les
  cartes se réorganisent lorsque la fenêtre est réduite (testé de 1024 × 700 à
  plein écran).

Le détail du système de design (palette, typographie, espacements, états,
animations) et toutes les captures de référence sont dans
[`docs/DESIGN.md`](docs/DESIGN.md).

---

## Fonctionnalités intégrées dans l'application (`OverLoad.exe`)

- **Application de bureau Windows native (`PySide6` / Qt)** avec thèmes **Sombre** et **Clair**, courbe de débit en direct et préférences persistantes (`settings.json`).
- **Téléchargements simultanés** avec limite active configurable à chaud (`1` à `16`).
- **Pause, reprise HTTP Range (`206 Partial Content`) et reprise automatique** avec recul exponentiel après une coupure réseau ou une erreur temporaire du serveur (`408`, `429`, `5xx`), sans jamais perdre le fichier `.part`.
- **Détection intelligente des fichiers déjà présents** (dossier cible, file active, historique SQLite, ou `.part` reprenable) avec boîte de dialogue dédiée (*Ouvrir le dossier existant*, *Ignorer*, *Télécharger une copie « (2) »*).
- **Limite de vitesse globale** par seau à jetons partagé entre tous les téléchargements actifs pour ne jamais saturer Internet.
- **Téléchargement par lots** depuis une liste de liens collée ou un fichier `.txt`.
- **Historique persistant SQLite** (`library.db`) et bouton **Ouvrir / Rouvrir le dossier** sélectionnant directement le fichier dans l'Explorateur Windows (`explorer.exe /select,...`).
- **Télémétrie temps réel** : vitesse réelle sur fenêtre glissante, temps restant estimé lissé et diagnostic des éventuels problèmes de connexion.

## 🎬 Espace Créateurs

L'onglet **Espace Créateurs** de l'application native rassemble tout le nécessaire pour préparer un projet vidéo sans risque pour vos fichiers d'origine :

- **Préparer un dossier complet pour chaque projet vidéo** : arborescence propre (rushs, audio, images, sous-titres, projets, exports) créée en un clic, avec fichier `LISEZ-MOI.txt` et manifeste `overload-projet.json` rappelant les règles. Un dossier existant est enrichi, jamais vidé ni écrasé.
- **Importer et organiser des médias destinés au montage** : les fichiers sont classés par type (vidéo, audio, image, sous-titres) dans les dossiers du profil choisi, avec un **plan détaillé avant toute copie**.
- **Renommer des lots de fichiers avec des modèles personnalisés** : jetons `{projet}`, `{nom}`, `{origine}`, `{type}`, `{ext}`, `{date}`, `{annee}`, `{mois}`, `{jour}`, `{heure}` et `{numero}` (padding possible : `{numero:03}`), aperçu en direct, et jamais d'écrasement (suffixe « (2) », « (3) »… ou fichier laissé intact).
- **Créer des sous-titres et gérer les pistes disponibles** : liste de toutes les pistes d'un média (langues, canaux, pistes par défaut/forcées), extraction d'une piste de sous-titres en `.srt` converti, extraction d'une piste audio en `.wav` PCM, et création d'un modèle `.srt` UTF-8 prêt à compléter. Le média source n'est jamais modifié.
- **Exporter une liste des sources, codecs et caractéristiques des fichiers** : inventaire CSV (UTF-8 BOM, séparateur « ; », ouverture directe dans Excel) avec conteneur, codecs vidéo/audio, résolution, FPS, durée, nombre de pistes, taille et **adresse source du téléchargement** quand le fichier provient de l'historique OverLoad.
- **Profils dédiés aux logiciels de montage** : profils intégrés **Adobe Premiere Pro**, **DaVinci Resolve**, **Final Cut Pro (Mac)**, **CapCut / débutant** et **Universel** (structure + formats d'importation recommandés), complétés par vos **profils personnalisés** persistants.
- **Le mode « Préparer mon projet »** : rassemble des médias dispersés (fichiers ou dossiers entiers) dans une structure de dossiers propre, **sans déplacer ni écraser les originaux sans confirmation** — seules des copies sont créées, après validation du plan, et chaque destination existante est signalée comme conflit à trancher (ignorer ou copie « (2) »).

Règles de sécurité appliquées partout dans l'espace Créateurs : vos fichiers d'origine ne sont **jamais déplacés, renommés, modifiés ou supprimés** ; aucune copie n'est effectuée sans confirmation explicite ; aucun fichier existant n'est jamais écrasé.

## Analyseur multimédia Windows

L'onglet **Analyse multimédia** de l'application native permet de sélectionner un fichier local :

- conteneur, codecs, résolution, FPS moyens et débit global/par piste (si renseigné) ;
- toutes les pistes vidéo, audio et sous-titres, langues, canaux et pistes par défaut/forcées ;
- vérification optionnelle par décodage complet audio/vidéo, sans modifier le fichier ;
- alertes avant importation : codecs moins courants, couleurs 10 bits/4:2:2, cadence
  potentiellement variable, conteneurs et sous-titres peu acceptés ;
- bouton **« Pourquoi ce fichier ne fonctionne-t-il pas ? »** avec des explications
  simples et des pistes de résolution, sans conversion automatique de l'original.

La vérification complète peut prendre jusqu'à 10 minutes (analyse des métadonnées :
60 secondes maximum). Un dépassement de délai est **indéterminé**, pas une preuve de
corruption. Aucun outil ne peut garantir qu'un fichier lisible contient toute la fin
attendue sans comparaison avec l'original. Les alertes de compatibilité sont générales,
pas une certification pour une version précise d'un logiciel de montage.

FFmpeg et FFprobe LGPL sont embarqués dans les distributions Windows. En développement,
installez ces deux outils dans le PATH. Leurs processus n'accèdent qu'aux fichiers locaux.

---

## Compiler l'exécutable Windows (`OverLoad.exe`)

Chaque push déclenche automatiquement la compilation sur **GitHub Actions (`windows-latest`)** et publie l'artefact **`OverLoad-Windows-x64`** contenant :
- `OverLoad.exe` — exécutable autonome tout-en-un prêt à lancer sans installation ;
- `OverLoad-Setup.exe` — installateur Windows 11 en français (Inno Setup) ;
- `OverLoad-Portable-win64.zip` — version portable isolée (`OverLoad-data\`) ;
- `SHA256SUMS.txt` — empreintes SHA-256 vérifiables.

Chaque étiquette `v*` (par exemple `v1.0.0`) déclenche en plus le workflow
**Release OverLoad.exe** qui recompile tout, vérifie l'auto-test de l'exécutable et
publie une **release GitHub** avec `OverLoad.exe`, `OverLoad-Setup.exe`,
`OverLoad-Portable-win64.zip` et `SHA256SUMS.txt`.

Pour compiler `OverLoad.exe` en local sous Windows (Python 3.11+ et GitHub CLI `gh`) :

```powershell
python -m pip install -e ".[dev,build]"
python scripts/prepare_ffmpeg.py
python scripts/build_windows.py
```

Pour lancer directement en développement :

```powershell
overload
```

---

## Qualité et tests

- Audit initial, licences et architecture cible : [`docs/audit/PHASE0_AUDIT.md`](docs/audit/PHASE0_AUDIT.md)
- Composants tiers et licences : [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)
- Licence du projet : [MIT](LICENSE)

```bash
python -m ruff check src tests scripts
python -m pytest
```

Pour régénérer les captures de référence de l'interface :

```bash
python scripts/render_screenshots.py
```
