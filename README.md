# OverLoad

⚡ **OverLoad** — Organise et prépare tes médias.

🎬 Télécharge des fichiers depuis des adresses directes prises en charge, retrouve tes vidéos, musiques et images, analyse-les et convertis-les, directement dans une **application native Windows (`OverLoad.exe`)** sans dépendance à installer.

**Sources prises en charge (version 1) :** adresses HTTP(S) qui pointent directement vers un fichier. OverLoad ne contourne ni les protections d'accès, ni les DRM, ni les restrictions d'une plateforme.

**OverLoad — Your media, your way.**

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
