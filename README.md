# OverLoad
⚡ **OverLoad** — Download. Save. Enjoy.  🎬 Télécharge et organise tes vidéos préférées avec simplicité. 🚀 Rapide, moderne et pensé pour une expérience fluide.  **OverLoad — Your media, your way.**

---

## Développement

> État : phase de fondation. OverLoad ne fournit pas encore d'exécutable.

- Audit initial, licences et architecture cible : [`docs/audit/PHASE0_AUDIT.md`](docs/audit/PHASE0_AUDIT.md)
- Composants tiers et licences : [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)
- Licence du projet : [MIT](LICENSE)

Lancer les tests (Python 3.11 ou plus) :

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest
```

Pour la version 1, seules les adresses HTTP(S) qui pointent directement vers un fichier sont acceptées.
