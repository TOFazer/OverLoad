# OverLoad

⚡ **OverLoad — Your media, your way.** Un projet en développement pour récupérer et préparer des médias.

## Disponible aujourd'hui / Available now

- **Téléchargement de fichiers directs HTTP(S)** via une interface PySide6 ou la ligne de commande. Ajout d'URL, file de 2 tâches en parallèle, pause, reprise, annulation, dossier personnalisable et état conservé entre les sessions.
- Fichiers écrits en `.part`, jamais publiés comme terminés si vides ou si la taille annoncée est différente ; validation SHA-256 **si l'utilisateur fournit une empreinte de confiance** en ligne de commande.
- Redirections et adresses IP contrôlées à chaque connexion ; accès aux réseaux privés bloqué par défaut, proxy système désactivé. Limite de 10 Gio par fichier.
- Reprise HTTP Range seulement si le serveur fournit ETag (fort) ou Last-Modified et si le fichier partiel correspond à la même URL ; si le serveur ignore Range, on recommence sans concaténer.

**Ne fonctionne pas pour :** pages de plateformes vidéo, contenus DRM, flux protégés, fichiers nécessitant un compte ou navigateur. Une URL de page Web n'est pas l'URL directe du fichier. Aucun contournement d'accès n'est prévu. N'utilisez OverLoad que pour des fichiers que vous avez le droit de télécharger.

> **Pas encore de version installable** : aucun `.exe`, installateur, convertisseur, bibliothèque ou intégration Premiere/Resolve n'est publié. L'interface nécessite actuellement Python et PySide6. Certaines connexions d'entreprise utilisant un proxy obligatoire ne fonctionneront pas.

## Démarrer (développement / Windows)

Python 3.11+ requis. Depuis le dépôt :

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui]"
.venv\Scripts\python -m overload
```

Collez une URL **directe** HTTP(S), choisissez le dossier, puis cliquez sur **Ajouter à la file**. Utilisez **Pause**, **Reprendre / Réessayer** ou **Annuler** après avoir sélectionné une ligne. La fermeture met les téléchargements en cours en pause ; ils peuvent être repris après redémarrage. Les tâches qui étaient actives au moment d'un arrêt brutal sont relancées au prochain démarrage. Les tâches mises en pause restent en pause.

Sans interface (Python 3.11+) :

```bash
python -m pip install -e .
python -m overload download "https://example.org/media/clip.mp4" --folder ./medias
# Si l'éditeur fournit une empreinte :
python -m overload download "https://example.org/media/clip.mp4" --folder ./medias --sha256 <64-caracteres-hexadecimaux>
```

Relancer **la même commande** reprend un `.part` identifié par sa métadonnée et le validateur du serveur ; sinon un nouveau fichier reçoit un suffixe `(2)`. La commande imprime l'empreinte locale SHA-256 après un téléchargement sans empreinte fournie : elle ne prouve **pas** à elle seule l'authenticité de la source. Sans taille connue fournie par le serveur ni empreinte de confiance, une coupure « normale » anticipée ne peut pas être détectée avec certitude.

Les tâches de l'interface sont conservées sous `%APPDATA%\OverLoad-Dev\downloads.json` (ou `~/.config/OverLoad-Dev/downloads.json` sous Unix). Ce fichier et les métadonnées `.part.json` contiennent les URL **en clair**, y compris d'éventuels jetons en paramètres d'URL : protégez leur accès et évitez de partager ces fichiers. Ne lancez pas plusieurs instances sur le même dossier et fichier d'état : le verrouillage interprocessus n'est pas encore disponible. L'annulation supprime le fichier partiel mais n'efface jamais un fichier terminé.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest
```

Les tests d'intégration utilisent un serveur HTTP local **uniquement en mode test**, pour simuler les reprises, coupures, redirections et erreurs. En fonctionnement normal, les adresses privées restent refusées.

## Roadmap / Planned (not available yet)

1. Distribution Windows testée sur une machine propre, installateur, journaux et mise à jour vérifiée.
2. Analyse médias via ffprobe, diagnostic de compatibilité montage et aperçu.
3. Bibliothèque, projets de montage, export de métadonnées et détection des fichiers manquants.
4. Conversion/remux avec FFmpeg et originaux conservés ; connecteurs officiels/autorisation par source.

Voir [l'audit initial](docs/audit/PHASE0_AUDIT.md) pour les décisions techniques, [les licences tierces](THIRD_PARTY_LICENSES.md) et [la politique de sécurité](SECURITY.md). Le document d'audit est un **instantané historique** ; cette page décrit l'état actuel du code.

---

## English quick start

OverLoad currently downloads **direct HTTP(S) files only**; video platform pages, DRM, login-required media and conversion are not supported. There is **no released installer/executable yet**. With Python 3.11+: `python -m pip install -e ".[gui]"` then `python -m overload` for the desktop queue, or `python -m overload download "https://example.org/file.mp4" --folder ./media` for the CLI. Paused downloads can resume when the server supports validated byte ranges; otherwise the file restarts from zero. Downloads are capped at 10 GiB and private/local network addresses are blocked. Run `python -m pip install -e ".[dev]" && python -m pytest` to test.
