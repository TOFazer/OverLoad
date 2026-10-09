# OverLoad

⚡ **OverLoad** — Organise et prépare tes médias.

🎬 Télécharge des fichiers depuis des adresses directes prises en charge, retrouve tes vidéos,
musiques et images, analyse-les et convertis-les, sans installer de dépendances.

**Sources prises en charge (version 1) :** adresses HTTP(S) qui pointent directement vers un fichier.
OverLoad ne contourne ni les protections d'accès, ni les DRM, ni les restrictions d'une plateforme.

> État : développement en cours. Une première version de test (`OverLoad.exe`) est produite
> par GitHub Actions et téléchargeable dans les artefacts de la dernière exécution réussie.
> Voir [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md). Ce n'est pas encore une version publique.

**OverLoad — Your media, your way.**

---

## Développement

- Audit initial, licences et architecture cible : [`docs/audit/PHASE0_AUDIT.md`](docs/audit/PHASE0_AUDIT.md)
- Composants tiers et licences : [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)
- Licence du projet : [MIT](LICENSE)
- Construction Windows : [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md)

Lancer l'application depuis les sources (Windows) :

```powershell
python -m pip install -e ".[dev]"
python -m overload
```

Lancer les tests (Python 3.11 ou plus) :

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest
```

Pour la version 1, seules les adresses HTTP(S) qui pointent directement vers un fichier sont
acceptées. Les adresses locales ou privées (localhost, 192.168.x.x, etc.) sont refusées, y compris
lorsqu'un nom de domaine y redirige.
