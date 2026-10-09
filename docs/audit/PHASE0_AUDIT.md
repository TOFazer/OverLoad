# OverLoad — Audit initial (Phase 0)

> Document de travail. Date : 2026-10-09. Branche : `arena/0c60ad48-overload` (base : `main` @ `c3cb69f`).

Ce document répond aux points 1 à 10 de la Phase 0 du plan de développement, à partir de l'état réel du dépôt. Les choix marqués **[DÉCISION n]** ont été tranchés par le propriétaire du projet ; le statut de chacun figure en section 15.

---

## 1. État constaté du dépôt

| Élément | Constat |
|---|---|
| Dépôt | `TOFazer/OverLoad`, public, créé le 2026-10-09 |
| Historique | 1 seul commit (`Initial commit`) |
| Contenu | `README.md` uniquement (2 lignes de description) |
| Langage détecté par GitHub | Aucun |
| Taille | 0 Ko |
| Licence | **Aucune** (`licenseInfo: null`) |
| Releases / PR / issues | Aucune |
| Branches distantes | `main` uniquement |
| Dépôt `TOFazer/OverLoadDev` | **N'existe pas** |

**Conséquence :** il n'existe ni code à auditer, ni fonctionnalité opérationnelle, ni bug, ni test, ni dépendance. La Phase 0 consiste donc surtout à **définir l'architecture et les règles** avant d'écrire du code. Il n'y a rien à « réécrire » ; la question de la réécriture ne se pose pas.

**Points à corriger dès maintenant :**

- **Licence absente.** Sans licence, personne n'a le droit légal d'utiliser, copier ou redistribuer le code. Il faut en choisir une avant toute publication d'exécutable (voir §6).
- **Le README promet « Télécharge et organise tes vidéos préférées ».** Cette formulation laisse entendre que n'importe quelle URL est téléchargeable, ce que le plan interdit explicitement (§7.1). Le message public devra être réaligné sur la liste des sources prises en charge.

---

## 2. Fonctionnalités réellement opérationnelles

**Aucune.** Le dépôt ne contient aucun code exécutable. Les fonctionnalités du plan sont donc toutes à construire, dans l'ordre des phases.

## 3. Bugs identifiés

**Aucun** (pas de code). Les risques à surveiller dès le départ sont listés en §8.

## 4. Dépendances

**Aucune** pour l'instant. Les composants candidats et leur licence sont listés en §6.

## 5. Moteurs de téléchargement, interface, tests

- Moteur de téléchargement existant : **aucun**.
- Composant d'interface existant : **aucun**.
- Tests existants : **aucun**.

---

## 6. Licences des composants candidats

Vérifiées le 2026-10-09 via l'API GitHub (licence déclarée par le dépôt) et les fichiers de licence.

| Composant | Rôle envisagé | Licence | Points d'attention |
|---|---|---|---|
| **FFmpeg** | Analyse et conversion | LGPL v2.1+ par défaut ; GPL v2+ si `--enable-gpl` (certaines parties) | Distribuer un build **LGPL** (sans `--enable-gpl`, sans `--enable-nonfree`), en binaire séparé, avec mention de licence et source disponible. Un build GPL impose la GPL à l'application entière. |
| **yt-dlp** | Moteur de téléchargement possible | Unlicense (domaine public) | Licence permissive. **Le risque est juridique et contractuel, pas technique** : beaucoup de plateformes interdisent le téléchargement dans leurs conditions d'utilisation. Voir la décision sur les sources (§9). |
| **PyInstaller** | Packaging Python en `.exe` | GPL v2 (ou ultérieure) avec exception « bootloader » | Exception vérifiée sur le texte officiel (`COPYING.txt`) : le bootloader embarqué peut être distribué librement dans un exécutable combiné ; la GPL reste applicable à PyInstaller lui-même. Validation juridique à faire avant diffusion. |
| **PySide6 (Qt for Python)** | Interface de bureau | LGPL v3 (ou version commerciale) | Respecter les obligations LGPL : permettre le remplacement de la bibliothèque, mentionner la licence. À vérifier au moment du packaging. |
| **Tauri** | Alternative (interface Web + Rust) | Apache-2.0 / MIT | Permissive. Demande d'apprendre Rust et de gérer un sidecar Python ou FFmpeg. |
| **Electron** | Alternative (interface Web) | MIT | Permissive. Application lourde (Chromium embarqué). |
| **mpv** | Lecteur éventuel | GPL v2+ ou LGPL selon options de build | À éviter sauf besoin précis, pour ne pas imposer la GPL. |
| **Inno Setup** | Installateur `OverLoad-Setup.exe` | Licence Inno Setup (gratuite, usage libre) | Vérifier les conditions de redistribution de l'outil généré. |

**Règle proposée :** chaque dépendance distribuée a une entrée dans `THIRD_PARTY_LICENSES.md`, avec sa licence, sa version et le texte de licence joint à l'installateur.

---

## 7. Technologie de bureau

Le plan demande de choisir selon le dépôt. Le dépôt étant vide, la décision se fait sur les besoins réels : fenêtre native Windows, traitement de fichiers, FFmpeg, base de données, mises à jour, installateur.

| Critère | Python + PySide6 + PyInstaller | Tauri 2 (Rust + Web) | Electron |
|---|---|---|---|
| Fenêtre Windows native | Oui (Qt) | Oui (WebView2) | Oui (Chromium) |
| Intégration yt-dlp | Native (Python) | Sidecar à gérer | Sidecar à gérer |
| Intégration FFmpeg | Simple (sous-processus) | Simple (sidecar) | Simple (sous-processus) |
| Taille de distribution | Moyenne (≈ 60–120 Mo, à mesurer) | Petite | Grande (≥ 100 Mo) |
| Courbe d'apprentissage | Faible si Python maîtrisé | Élevée (Rust) | Moyenne |
| Packaging Windows | PyInstaller + Inno Setup | Intégré (MSI/NSIS) | electron-builder |
| Mises à jour | À construire (ou outil dédié) | Plugin officiel | electron-updater |

**Recommandation (à valider) :** **Python 3.12 + PySide6 + SQLite + FFmpeg LGPL en binaire séparé + PyInstaller + Inno Setup**, avec GitHub Actions sur `windows-latest`.

Raisons : le traitement de fichiers, yt-dlp et l'appel à FFmpeg sont naturels en Python, la séparation des modules est simple à tester avec `pytest`, et la chaîne de build reste compréhensible pour un mainteneur seul. Le principal coût est la taille du livrable et la maintenance de l'interface Qt, à mesurer dès le prototype.

**[DÉCISION 1]** Validée : Python + PySide6.

---

## 8. Risques identifiés

| Risque | Impact | Mesure proposée |
|---|---|---|
| Violation de conditions d'utilisation d'une plateforme | Juridique, retrait du projet | Liste blanche de sources et d'usages, validée avant toute intégration (§9) |
| Distribution d'un FFmpeg GPL par erreur | Obligation de licence GPL pour tout l'exécutable | Build LGPL figé, vérifié à chaque release (`ffmpeg -version`, `-buildconf`) |
| Mise à jour remplaçant des fichiers non vérifiés | Corruption, exécution de code tiers | Signature + SHA-256 obligatoires avant installation (Phase 3) |
| Écrasement de fichiers personnels | Perte de données | Aucune suppression ni écrasement sans confirmation explicite |
| Données de la version stable touchées par une version dev | Perte de projets et de préférences | Dossiers de données séparés par canal |
| Support de Windows 10 | Insécurité, promesse non tenue | Voir §10 |
| Secrets de publication dans le code | Compromission de la chaîne de publication | Secrets uniquement dans GitHub Actions (environnement protégé) |

---

## 9. Sources et conformité (décision bloquante pour Phase 1)

Le plan demande de ne télécharger que depuis des **sources officiellement prises en charge et autorisées**, sans contourner DRM ni protections. Il faut donc :

1. Définir une **liste blanche** de sources (par exemple : fichiers accessibles directement via une URL HTTP(S) fournie par l'utilisateur, flux publics dont les conditions autorisent le téléchargement, sources partenaires).
2. Désactiver tous les extracteurs yt-dlp hors de cette liste, plutôt que de les laisser disponibles par défaut.
3. Afficher, pour chaque source, une explication de ce qui est et n'est pas permis.

**[DÉCISION 2]** Validée : fichiers directs HTTP(S) uniquement en v1.

---

## 10. Versions Windows prises en charge

Constat au 2026-10-09 :

- Windows 10 a fini son support standard le **14 octobre 2025**.
- Le programme ESU grand public pour Windows 10 prend fin le **13 octobre 2026**, soit dans quatre jours. Il n'est pas prolongeable pour les particuliers.
- Windows 11 64 bits est la seule cible réellement maintenable sur la durée.

**Proposition :** annoncer officiellement **Windows 11 64 bits**. Windows 10 22H2 peut être testé sans être annoncé comme pris en charge. Cette décision doit être confirmée avant la Phase 2 (plan §3.5 : « vérifier avant de les annoncer »).

**[DÉCISION 3]** Confirmer Windows 11 64 bits comme cible officielle.

---

## 11. Architecture cible

### 11.1 Découpage des modules

```
overload/
  core/        configuration, chemins de données, journalisation, erreurs, traductions (i18n)
  ui/          fenêtre principale, sections, thèmes, notifications (aucune logique métier)
  downloads/   moteur, file d'attente, états de tâche, doublons, reprise
  library/     base SQLite, indexation, collections virtuelles, tags, favoris
  media/       analyse (ffprobe), contrôle d'intégrité, rapports
  convert/     profils FFmpeg, tâches de conversion, lots, annulation
  creators/    projets, structure de dossiers, inventaire, médias manquants
  updates/     manifeste de version, téléchargement, vérification, installation, journal
  settings/    préférences persistantes, export/import
  history/     journal universel des opérations
tests/
  unit/  integration/  scenarios/  fixtures/ (médias générés à la volée, jamais commités)
```

Règle : `ui/` n'appelle que les services ; les services ne dépendent jamais de `ui/`. Cela permet de tester la logique sans interface.

### 11.2 Dépôts

**OverLoad (public, source de référence)**
- Code de l'application, tests stables, scripts de build, workflows de publication, documentation publique, `THIRD_PARTY_LICENSES.md`, changelog, feuille de route publique.

**OverLoadDev (développement, privé si souhaité)**
- Prototypes, moteurs expérimentaux, outils de diagnostic, tests de compatibilité, essais FFmpeg et codecs, builds de développement, notes techniques.
- Ne contient **pas** de copie de l'application : il importe ou référence des composants de OverLoad.

**Passage de OverLoadDev vers OverLoad** : par pull request uniquement, avec une checklist (tests passants, licence vérifiée, pas de secret, pas de fichier média, doc mise à jour). Aucune synchronisation automatique.

### 11.3 Canaux de distribution

| Canal | Par défaut | Données | Mises à jour proposées |
|---|---|---|---|
| Stable | Oui | `%APPDATA%\OverLoad` | Stable uniquement |
| Bêta | Non (action volontaire + avertissement) | `%APPDATA%\OverLoad-Beta` | Bêta et stable |
| Développement | Non (avertissement fort) | `%APPDATA%\OverLoad-Dev` | Tous, jamais proposé aux utilisateurs Stable |

Version portable : données dans `OverLoad-data\` à côté de l'exécutable, temporaires dans `%LOCALAPPDATA%\OverLoad\Temp`, jamais mélangés aux fichiers personnels.

### 11.4 Données

| Donnée | Emplacement | Sauvegarde / migration |
|---|---|---|
| Paramètres | `settings.json` (versionné) | Migration par numéro de schéma |
| Historique et bibliothèque | SQLite (`library.db`, versionné) | Sauvegarde avant migration |
| Projets | Dossiers choisis par l'utilisateur, référencés en base | Jamais déplacés par l'application |
| Journaux | `logs\` (rotation) | Inclus dans le rapport de diagnostic sur demande |
| Temporaires | `Temp\` | Nettoyés à la fermeture et sur demande |
| Téléchargements | Dossier choisi par l'utilisateur | Jamais supprimés automatiquement |

---

## 12. Liste de tâches (Phases 1 à 9)

Légende : ✅ fait · ⬜ à faire.

### Phase 0 — Audit et organisation
- ✅ 1. Examiner le dépôt
- ✅ 2. Identifier la technologie (aucune — dépôt vide)
- ✅ 3. Comprendre le fonctionnement actuel (aucun code)
- ✅ 4. Lister les fonctionnalités opérationnelles (aucune)
- ✅ 5. Identifier les bugs (aucun code ; risques en §8)
- ✅ 6. Repérer les dépendances (aucune)
- ✅ 7. Vérifier les licences des composants candidats (§6)
- ✅ 8. Définir l'architecture cible (§11)
- ✅ 9. Créer la liste de tâches (§12)
- ✅ 10. Définir les critères de réussite (§13)
- ✅ Choisir la technologie (DÉCISION 1 : Python + PySide6)
- 🟡 Créer le dépôt `OverLoadDev` (privé, DÉCISION 5) — **non créé** : l'intégration GitHub n'a pas la permission de création de dépôt ; à créer manuellement ou à autoriser
- ✅ Ajouter une licence à `OverLoad` (MIT, DÉCISION 4)

### Phase 1 — Fiabilisation
- ✅ Socle : structure `src/overload/`, `pyproject.toml`, `pytest`, `ruff`, CI Windows (`.github/workflows/ci.yml`)
- ✅ Machine d'états des tâches (`downloads/state.py`) : « Terminé » accessible uniquement depuis « Finalisation »
- ✅ « Terminé » seulement après vérification (taille non nulle, taille annoncée respectée), écriture dans `.part` puis renommage
- ✅ Détection des fichiers incomplets et de taille nulle ; le `.part` est conservé pour reprise (HTTP Range)
- ✅ Chemins de destination : dossier absent refusé, noms existants jamais écrasés (« (2) »), noms Windows sûrs
- ✅ Validation des URL : schémas HTTP(S) seulement, identifiants refusés, adresses locales/privées refusées, redirections revalidées
- ✅ Messages d'erreur structurés (`core/errors.py` : ce qui a échoué, cause, action)
- ✅ Protection DNS rebinding : résolution unique par connexion, toutes les adresses contrôlées, connexion uniquement aux adresses validées, SNI et certificat vérifiés sur le nom d'origine, proxy désactivé (`downloads/netguard.py`)
- ⬜ Pause effective du téléchargement, file d'attente et limite de tâches simultanées (couche suivante)
- ⬜ Traductions FR/EN des messages d'erreur (aujourd'hui en français uniquement)
- ✅ Sources v1 : fichiers directs HTTP(S) uniquement (DÉCISION 2)

### Phase 2 — Application Windows autonome
- ⬜ Fenêtre principale, navigation, thème clair/sombre/système
- ⬜ Paramètres persistants (schéma versionné)
- ⬜ Identité visuelle et icône
- ⬜ Textes centralisés (FR, EN) dans des fichiers de traduction
- ⬜ Build portable (`OverLoad.exe`) et installateur (`OverLoad-Setup.exe`)
- ⬜ Intégration FFmpeg LGPL et yt-dlp, licences dans `THIRD_PARTY_LICENSES.md`
- ⬜ Essais sur Windows 11 propre (machine virtuelle sans outils de développement)
- ⬜ Désinstallation vérifiée, données conservées

### Phase 3 — Lanceur et mises à jour
- ⬜ Manifeste de version par canal, publié sur GitHub Releases
- ⬜ Vérification SHA-256 puis signature avant toute installation
- ⬜ Fenêtre « Mettre à jour / Plus tard », notes de version, taille
- ⬜ Installation contrôlée, journal de mise à jour, récupération en cas d'échec
- ⬜ Tests de mises à jour successives sur une installation de test

### Phase 4 — Expérience grand public
- ⬜ Accueil, historique universel, notifications Windows
- ⬜ Bibliothèque (vues, filtres, favoris, tags, collections virtuelles)
- ⬜ Import de fichiers locaux sans déplacement

### Phase 5 — Analyse et conversion
- ⬜ Analyse ffprobe et rapport exportable (avec limites du contrôle affichées)
- ⬜ Convertisseur avec profils testés sur de vrais fichiers
- ⬜ Original conservé par défaut ; annulation avec nettoyage des temporaires

### Phase 6 — Espace Créateurs
- ⬜ Profils de préparation, structure de projet configurable
- ⬜ Inventaire exportable, détection des médias manquants (sans déplacer ni supprimer)
- ⬜ Ouverture de dossier, révélation dans l'Explorateur, copie de chemin

### Phase 7 — OverLoadDev
- ⬜ Création du dépôt, définition du périmètre (§11.2)
- ⬜ Outils de diagnostic, procédure de passage vers OverLoad

### Phase 8 — Publication
- ⬜ Build reproductible, sommes de contrôle, notes de version
- ⬜ Test de la procédure de récupération
- ⬜ Première version stable quand les critères (§13) sont remplis

### Phase 9 — Long terme
- ⬜ Recherche avancée, prévisualisation, nouvelles sources, localisation

---

## 13. Critères de réussite (plan §22)

Chaque critère sera vérifié par un test automatisé ou une procédure écrite. Ceux qui ne peuvent pas être automatisés figurent dans `docs/RELEASE_CHECKLIST.md` (à créer en Phase 8).

| Critère | Vérification prévue |
|---|---|
| Démarrage sur Windows 11 propre | Essai en VM sans outils de développement |
| Aucune installation manuelle | Essai en VM ; vérifier que le build embarque ses dépendances |
| Portable et installateur fonctionnent | Scénarios d'essai documentés |
| Erreurs compréhensibles | Tests unitaires sur les messages (FR et EN) |
| Fichiers incomplets non déclarés terminés | Test d'intégration : coupure réseau simulée |
| Bibliothèque ne supprime pas les sources | Test : retrait d'un élément, fichier toujours présent |
| Analyse fiable dans les limites des composants | Tests sur fichiers générés connus + mention des limites dans le rapport |
| Conversion conserve l'original | Test : sortie dans un autre dossier, original inchangé |
| Paramètres persistants | Test : redémarrage simulé |
| Mises à jour vérifiées | Test : fichier altéré rejeté |
| Projets et téléchargements survivent aux mises à jour | Test de mise à jour successive |
| Canaux séparés | Test : une version dev ne propose jamais la stable à un utilisateur stable, et inversement |
| Tests principaux passent | CI Windows verte |
| Licences vérifiées | `THIRD_PARTY_LICENSES.md` complet, relu |
| Documentation | Installation, usages, limites |
| Publication reproductible | Build reproduit depuis un tag, sommes comparées |

---

## 14. Actions hors dépôt

- **Dépôt `TOFazer/OverLoadDev`** : à créer en privé. La création a échoué (`Resource not accessible by integration`) : l'intégration GitHub de la session n'a pas la permission de créer un dépôt. Il faut le créer manuellement ou accorder cette permission.
- **Secrets de publication.** Aucun secret n'est nécessaire pour la Phase 0. Ils seront configurés dans GitHub Actions (environnement protégé) en Phase 3.

---

## 15. Décisions

| # | Décision | Statut |
|---|---|---|
| 1 | Technologie : Python 3.12 + PySide6 + SQLite + FFmpeg LGPL + PyInstaller + Inno Setup | **Validée** |
| 2 | Sources de la première version : **URL de fichiers directs (HTTP/HTTPS) uniquement**. Aucun extracteur de plateforme ; yt-dlp n'est pas intégré en v1. | **Validée** |
| 3 | Windows 11 64 bits comme cible officielle | À confirmer en Phase 2 |
| 4 | Licence de OverLoad : **MIT** | **Validée** (fichier `LICENSE` ajouté) |
| 5 | Dépôt `OverLoadDev` : **privé** (choix validé, création **en attente** : permission manquante) | Validée, action restante |

Conséquence de la décision 2 : yt-dlp est retiré de la v1 et la section 6 le concerne uniquement pour une étude ultérieure. Toute source supplémentaire exigera une vérification écrite de ses conditions d'utilisation avant intégration.
