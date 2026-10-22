# OverLoad

⚡ **OverLoad** — Organise et prépare tes médias.

🎬 Télécharge des vidéos YouTube et des fichiers depuis des adresses directes, retrouve tes vidéos, musiques et images, analyse-les, prépare tes projets de montage et organise tes médias, directement dans une **application native Windows (`OverLoad.exe`)** sans dépendance à installer.

**Sources prises en charge :** vidéos YouTube publiques (`youtube.com/watch?v=…`, `youtu.be/…`, `youtube.com/shorts/…`) et adresses HTTP(S) qui pointent directement vers un fichier. OverLoad ne contourne ni les protections d'accès, ni les DRM, ni les restrictions d'une plateforme : les vidéos privées, réservées aux membres ou soumises à un contrôle d'âge sont refusées avec un message explicite.

**OverLoad — Your media, your way.**

---

## 🌲 OverLoad 2.0 — une vraie refonte, pensée pour l'usage quotidien

OverX impressionne quand on le découvre ; OverLoad doit impressionner quand on
l'**utilise**. La version 2.0 repart de cette idée : même famille visuelle
(sombre, élégante, vert forêt naturel), mais une organisation entièrement
repensée pour qu'on sache toujours où l'on est, où sont les fichiers et
quoi faire ensuite.

**Nouvelle identité, partout la même** (fenêtre native, installateur,
interface web de secours) :

| Rôle | Couleur |
| --- | --- |
| Fond principal — vert-noir profond | `#101713` |
| Panneaux — navigation, contenu, menus | `#1A261F` |
| Vert forêt — actions principales, sélection, boutons | `#315E43` |
| Vert sauge — détails lumineux, accents graphiques | `#A9C7AE` |

Les couleurs d'état restent distinctes : succès lumineux pour « Terminé »,
ambre pour les avertissements, terracotta pour les erreurs, bleu-gris pour
l'information et la pause.

**Une organisation claire** — barre latérale fixe et sept sections stables :
**Accueil** (démarrer vite + activité récente), **Téléchargements** (tâches
en cours, en attente, en pause ou en erreur, avec pastille compteur),
**Bibliothèque** (nouveau : retrouver, filtrer et ouvrir les fichiers déjà
sur le disque, source de téléchargement incluse quand elle est connue),
**Espace Créateurs**, **Historique** (page dédiée), **Paramètres** et
**Aide** (nouveau : démarrage rapide, dépannage et raccourcis
`Ctrl+1`…`Ctrl+7`). L'analyse multimédia rejoint les Créateurs, avec les
outils de montage.

**Un écran de téléchargement en trois étapes** sur l'accueil : ① coller un
lien (bouton *Coller*, sources prises en charge expliquées), ② choisir les
options utiles (destination, qualité YouTube), ③ lancer. Chaque tâche
affiche un statut explicite et ses seules actions pertinentes (pause,
reprise, relance, annulation, **ouvrir le fichier**, afficher le dossier),
et la progression reflète les octets réellement écrits : **100 % signifie
fichier complet et vérifié** — jamais avant.

**Un Espace Créateurs qui se comprend tout seul** : huit cartes « Que
voulez-vous faire ? » (préparer un projet, analyser un fichier, vérifier
pour Premiere Pro, sous-titres, renommage, inventaire, profils) expliquent
chaque outil, les fichiers acceptés et l'effet produit **avant** de
l'ouvrir. La règle d'or ne change pas : les originaux ne sont jamais
déplacés, renommés, modifiés ou écrasés.

Captures et système de design complet : [`docs/DESIGN.md`](docs/DESIGN.md).

---

## Nouvelle identité « OverX Forest » + sélecteurs corrigés (v1.3)

- 🌲 **OverX Forest, pour OverLoad uniquement** : forêt de nuit naturelle et
  premium — vert sapin `#14251B` et charbon `#202722` en fonds, vert forêt
  `#244A35` en couleur de marque, vert mousse `#52765B` pour les boutons, vert
  sauge `#A8BFA5` en détails, crème naturel `#E8EDE5` pour le texte. Fini le
  violet/bleu « gaming » par défaut : « Forêt » devient l'accent par défaut
  (les autres accents restent disponibles dans Paramètres → Apparence, et un
  ancien réglage resté sur le violet par défaut migre automatiquement).
  L'icône de l'application et du programme d'installation suit la même
  identité (éclair crème sur dégradé mousse → sapin).
- 📂 **Sélecteurs de fichiers corrigés** : cliquer sur « Parcourir… » /
  « Choisir… » n'ouvre plus la boîte « n'importe où ». Elle démarre toujours
  au bon endroit : dossier du fichier déjà indiqué dans le champ, sinon
  dernier dossier choisi dans OverLoad, sinon dossier de destination des
  téléchargements, sinon `Téléchargements`. Cela concerne l'accueil, les
  paramètres, l'analyse multimédia et tout l'espace Créateurs.

---

## YouTube → un vrai fichier MP4 (v1.2)

Collez un lien YouTube dans l'accueil, OverLoad s'occupe du reste :

1. **Reconnaissance du lien et métadonnées** — OverLoad détecte la vidéo, récupère
   son **titre**, son auteur, sa **durée**, sa **miniature** et les **qualités
   disponibles**, puis nomme le fichier avec le titre réel.
2. **Téléchargement des vrais flux** — les pistes vidéo et audio sont téléchargées
   séparément avec [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) (intégré à
   l'exécutable, aucune installation à faire).
3. **Fusion en MP4 avec FFmpeg** — le conteneur MP4 est privilégié et le couple
   **H.264 + AAC** est choisi en priorité pour maximiser la lecture dans VLC,
   Windows et l'import dans Adobe Premiere Pro.
4. **Vérification réelle du fichier** — la taille est contrôlée puis le fichier est
   analysé avec FFprobe : au moins une piste vidéo et une durée strictement
   positive sont exigées avant d'afficher « Terminé ». Un fichier vide ou
   purement audio n'est jamais déclaré réussi.

**Choix de la qualité** : menu déroulant à côté du bouton *Télécharger* —
« Meilleure disponible », 2160p, 1440p, 1080p, 720p, 480p, 360p. La qualité est
mémorisée par tâche et visible sur la carte de téléchargement.

**Progression, pause, annulation et limite de vitesse** restent identiques aux
téléchargements directs : la pause et l'annulation interrompent immédiatement
yt-dlp, et la limite de vitesse globale s'applique aussi aux flux YouTube.

**Compatibilité** : le MP4 H.264/AAC est le format le plus largement accepté, mais
aucun outil ne peut garantir l'import dans toutes les versions d'un logiciel de
montage. Les alertes de l'outil **Analyse** (Espace Créateurs) restent la référence.

**Limites assumées** : les vidéos privées, payantes, réservées aux membres,
soumises à un contrôle d'âge ou géo-bloquées ne sont pas téléchargeables (OverLoad
ne se connecte à aucun compte et ne contourne aucune protection). YouTube peut
modifier ses mécanismes à tout moment ; mettre à jour `yt-dlp` rétablit alors
l'extraction. Téléchargez uniquement les vidéos que vous êtes autorisé à
enregistrer, dans le respect du droit d'auteur et des conditions d'utilisation de
la plateforme.

---

## Une interface repensée (v1.1)

![Accueil d'OverLoad](docs/design/accueil.png)

La version 1.1 introduit une interface entièrement redessinée pour
`OverLoad.exe` :

- **Thème sombre premium par défaut**, **thème clair** complet et **couleurs
  d'accent** commutables en un clic, sans redémarrage (palette remplacée par
  OverX Forest en v1.3, voir ci-dessus).
- **Navigation latérale** : Accueil, Téléchargements, Créateurs, Analyse
  multimédia et Paramètres ; logo et nom OverLoad toujours visibles ; barre
  supérieure avec recherche globale, raccourci de téléchargement et accès
  rapide aux réglages.
- **Accueil actionnable** : champ de lien central collable (Ctrl+V) acceptant
  YouTube et les fichiers directs, sélecteur de **qualité vidéo**, validation en
  direct avec titre, auteur, durée et qualités disponibles, gros bouton
  **Télécharger**, dossier de destination
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
- **Vidéos YouTube en MP4** : métadonnées (titre, auteur, durée, miniature, qualités), choix de la qualité, fusion audio/vidéo FFmpeg et vérification FFprobe du fichier final.
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

L'outil **Analyse** de l'espace Créateurs (accessible aussi depuis la Bibliothèque, bouton « Analyser ») permet de sélectionner un fichier local :

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

`yt-dlp` (licence Unlicense) est également embarqué dans `OverLoad.exe` : aucune
installation Python n'est requise pour télécharger une vidéo YouTube. En
développement, `pip install -e .` l'installe automatiquement.

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
