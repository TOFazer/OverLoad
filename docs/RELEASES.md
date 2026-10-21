# Site de téléchargement et publication des releases

## Le principe

Le site public se trouve dans [`site/`](../site). Il est indépendant de l'interface
Web locale de l'application (`overload serve`). Il peut être hébergé sur GitHub Pages
ou sur n'importe quel hébergement statique, sans serveur ni secret.

Les boutons utilisent des URL GitHub **permanentes** :

- Installateur : <https://github.com/TOFazer/OverLoad/releases/latest/download/OverLoad-Setup.exe>
- Portable : <https://github.com/TOFazer/OverLoad/releases/latest/download/OverLoad-Portable-win64.zip>
- Empreintes : <https://github.com/TOFazer/OverLoad/releases/latest/download/SHA256SUMS.txt>

GitHub redirige `latest` vers la dernière release **stable**. Il faut conserver les
mêmes noms de fichiers d'une release à l'autre. Ne mettez pas de numéro de version
dans le nom des fichiers ni dans les liens du site.

**Il n'y a rien à modifier ni à redéployer sur le site pour une nouvelle version.**
Ces URL peuvent aussi être utilisées dans les boutons d'un autre site existant.

## 1. Activer le site une seule fois

Après intégration de ces fichiers dans `main` :

1. Dans le dépôt GitHub, ouvrir **Settings → Pages**.
2. Dans **Build and deployment → Source**, choisir **GitHub Actions**.
3. Dans **Actions**, lancer **Site de téléchargement (GitHub Pages)** avec
   **Run workflow** sur `main` (ou relancer le déploiement qui aurait échoué avant
   l'activation de Pages).
4. Attendre le succès du job `deploy`.

Adresse du site pour ce dépôt : **<https://tofazer.github.io/OverLoad/>**.
Le workflow affiche aussi l'adresse effective dans son environnement `github-pages`.
Il est nécessaire d'avoir les droits d'administration du dépôt pour activer Pages.
Les modifications suivantes de `site/` sur `main` seront déployées automatiquement.

Le workflow Pages ne déploie que `main`, pas les branches de développement.

## 2. Publier une nouvelle version de l'application

À répéter pour chaque version :

1. Intégrer les changements de l'application dans `main` et vérifier que la CI passe.
2. Ouvrir **Releases → Draft a new release** sur GitHub.
3. Créer un **nouveau tag** au format `v0.1.0`, puis `v0.1.1`, `v0.2.0`, etc.,
   avec `main` comme cible. Le tag doit pointer sur du code contenant le workflow
   de publication ; une ancienne release antérieure à ce workflow ne l'exécute pas.
4. Renseigner le titre et les notes. Pour une stable, ne pas cocher
   **Set as a pre-release** et sélectionner **Set as the latest release**.
5. Cliquer sur **Publish release**.
6. Attendre le succès du workflow **CI & Build Windows (.exe)** déclenché par
   l'événement `release`, notamment du job **Joindre les fichiers Windows à la release**.

Le workflow :

- récupère le code du **tag publié**, pas une autre branche plus récente ;
- aligne automatiquement les versions du paquet Python et de l'installateur sur ce tag ;
- exécute les tests Python et les tests du site ;
- compile les exécutables sous Windows, puis vérifie le démarrage réel d'OverLoad ;
- contrôle les empreintes SHA-256 et joint ces quatre fichiers à **cette release** :

```text
OverLoad.exe
OverLoad-Setup.exe
OverLoad-Portable-win64.zip
SHA256SUMS.txt
```

Les téléchargements du site suivent alors cette nouvelle version. Les simples push
restent des builds de développement dans les artefacts Actions : ils ne remplacent
pas la version publique. Aucun token personnel à configurer : seul le job de
publication reçoit le droit `contents: write` via le jeton fourni par GitHub Actions.

### Avant la première release ou pendant une compilation

Publier une release démarre le build : les fichiers n'arrivent qu'après quelques
minutes. La page interroge l'API publique GitHub pour afficher la version et vérifier
la présence de chaque fichier. S'il n'y a pas encore de stable, elle propose la liste
des releases ; si un fichier manque, elle propose la page de la release plutôt qu'un
lien de téléchargement cassé. Actualiser la page une fois le build terminé.

Si l'API est inaccessible ou son quota dépassé, les URL permanentes restent
accessibles, sans dépendre de cette API. Elles fonctionnent aussi sans JavaScript,
à condition qu'une stable avec les fichiers Windows soit déjà disponible.
Il n'y a aucune clé API dans le site.

### Si la compilation échoue

Consulter les logs dans **Actions**. Aucun exécutable ayant échoué aux tests ne sera
publié par ce workflow. Une fois le problème résolu, publier un nouveau tag, ou
utiliser **Re-run failed jobs** pour un incident temporaire. Le téléversement utilise
`--clobber` pour qu'une relance puisse terminer une publication partielle.
Ne réutilisez pas un ancien artefact de développement pour remplir une nouvelle release.

### Préversions

Tags acceptés : `v1.2.3-alpha.1`, `v1.2.3-beta.1`, `v1.2.3-rc.1`.
Cocher **Set as a pre-release** lors de leur publication. Le workflow compile et joint
également leurs fichiers, mais elles ne remplacent pas la stable sur le site.
Les trois composantes numériques doivent être comprises entre 0 et 65535 pour les
métadonnées Windows. Le numéro du tag n'a pas besoin d'être recopié dans le code.

## 3. Installation et mises à jour côté utilisateur

Le navigateur **télécharge** `OverLoad-Setup.exe`. L'utilisateur doit le lancer
explicitement sur Windows 11 x64 : une page Web ne peut pas installer une application
silencieusement.

Pour installer une nouvelle version, fermer OverLoad et exécuter le nouvel
installateur. L'`AppId` Inno Setup reste identique pour reconnaître l'installation
existante ; les données de l'application ne sont pas supprimées. Ce mécanisme
**ne constitue pas une mise à jour automatique dans l'application**.

Les fichiers ne sont pas signés par ce workflow. Les empreintes SHA-256 détectent
une altération de contenu mais ne remplacent pas une signature de code de l'éditeur.

## Développement du site

Aucune dépendance npm à installer. Les chemins de ressources sont relatifs pour
fonctionner sous `/OverLoad/` comme à la racine d'un autre hébergement.

```bash
node --test tests/web/releases.test.mjs
python -m http.server 8080 --bind 0.0.0.0 --directory site
```

Les tests couvrent les liens permanents, une nouvelle stable, l'absence de release,
les fichiers encore absents ou en cours d'envoi, les erreurs et quotas de l'API,
ainsi que l'exclusion des brouillons et préversions.
