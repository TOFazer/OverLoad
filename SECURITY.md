# Sécurité / Security

Pour signaler une vulnérabilité, **n'ouvrez pas d'issue publique** avec des détails d'exploitation. Utilisez l'option **Report a vulnerability** de l'onglet Security du dépôt GitHub, si disponible ; sinon contactez le mainteneur via son profil GitHub en demandant un canal privé. Précisez la version/commit, le scénario, l'impact et une reproduction minimale sans publier de secret.

Le moteur accepte seulement HTTP(S), vérifie les redirections et épingle les adresses DNS publiques de chaque connexion. Les proxys système sont désactivés pour ne pas contourner cette vérification. Les contrôles d'intégrité sont limités : la taille ne prouve pas l'authenticité ; fournissez une empreinte SHA-256 obtenue séparément d'une source fiable si nécessaire. Les URL et éventuels jetons sont enregistrés en clair dans l'état des tâches et les `.part.json`. Ne les partagez pas.

The current development build is not a sandbox for untrusted local users. Do not run multiple instances against the same state file or destination folder; there is no inter-process lock yet. No automatic updates or signed release artifacts are provided.
