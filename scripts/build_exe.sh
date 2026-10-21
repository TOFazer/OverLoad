#!/usr/bin/env bash
# Build approximatif sous Linux/macOS (test d'import, pas d'exe Windows réel).
set -e
echo "== OverLoad : vérification build =="
python -m pip install -e ".[dev,gui]" 2>&1 | tail -5
echo "-> Lancement tests..."
python -m pytest -q
echo "-> Vérification imports UI (sans affichage)..."
python -c "from overload.library.db import LibraryStore; from overload.library.organizer import OrganizerConfig; print('library OK')"
echo "OK — build Linux/macOS de vérification réussi. Pour l'exe Windows, lancer scripts/build_exe.ps1 sur Windows 11."
