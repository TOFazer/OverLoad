# Installateur OverLoad-Setup.exe (structure préparée, non compilée)

- `OverLoad.iss` : script Inno Setup. Installation par utilisateur (sans droits administrateur),
  raccourcis Menu Démarrer, raccourci Bureau facultatif, lancement facultatif après installation.
- Désinstallation : retire le programme. Les réglages (`%LOCALAPPDATA%\OverLoad`) et les
  téléchargements ne sont **pas** supprimés.

**Statut :** aucun `OverLoad-Setup.exe` n'est produit par la CI pour le moment. Étapes restantes :
1. valider la cible Windows (décision 3) ;
2. ajouter une étape de compilation Inno Setup dans le workflow `build-windows.yml` ;
3. tester l'installation, la mise à jour et la désinstallation sur une machine Windows propre.
