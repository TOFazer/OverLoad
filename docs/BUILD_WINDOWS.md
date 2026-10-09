# Construire et tester OverLoad sous Windows

## Obtenir OverLoad.exe depuis GitHub (sans installer quoi que ce soit)

1. Ouvrez le dépôt, onglet **Actions**.
2. Choisissez l'exécution **Build Windows** la plus récente qui est **verte** (réussie).
3. Dans la section **Artifacts**, téléchargez **OverLoad-windows-portable** : il contient
   `OverLoad.exe` et `SHA256SUMS.txt`.
4. Vérifiez la somme de contrôle avant de lancer le fichier :
   `certutil -hashfile OverLoad.exe SHA256`, puis comparez à `SHA256SUMS.txt`.

Les artefacts sont conservés 30 jours. Ce ne sont pas des versions publiques : une version
officielle sera publiée sur la page des Releases lors de la Phase 8.

## Ce que fait le workflow

| Étape | Rôle |
|---|---|
| `test` | Contrôle de style (ruff) et tests (pytest) sur Windows |
| `build` (après `test`) | Compilation PyInstaller de `packaging/overload.spec` |
| Auto-test | `OverLoad.exe --self-test` doit réussir (crée la fenêtre, sans l'afficher) |
| Sommes de contrôle | SHA-256 écrit dans `SHA256SUMS.txt` |
| Artefact | Publication de `OverLoad.exe` et `SHA256SUMS.txt` |

## Construire localement sur Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,build]"
python -m pytest
python -m PyInstaller packaging\overload.spec --noconfirm
.\dist\OverLoad.exe --self-test
```

## Où sont les données ?

- Par défaut : `%LOCALAPPDATA%\OverLoad` (réglages, journaux). Rien n'est écrit à côté de l'exécutable.
- Mode portable : créez un dossier `OverLoad-data` à côté de `OverLoad.exe`.
- Téléchargements : dossier choisi dans les paramètres (par défaut `Téléchargements\OverLoad`).
- Journal technique : `…\logs\overload.log` (à joindre à un signalement de bug).

## Limites de cette version

- Pas de signature numérique de l'exécutable : Windows SmartScreen peut afficher un avertissement
  pour un programme non signé. C'est attendu pour une version de test.
- L'installateur `OverLoad-Setup.exe` n'est pas encore produit (structure prête dans `installer/`).
- La CI Windows exécute le contrôle de style, les tests et l'auto-test de l'exécutable. Un essai
  d'installation et d'exécution sur une machine Windows propre reste à confirmer manuellement.
