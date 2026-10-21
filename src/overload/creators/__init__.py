"""Espace Créateurs : projets vidéo, organisation des médias et profils de montage.

Ce paquet regroupe toute la logique métier de l'onglet « Espace Créateurs » :
- `models` : structures de données (types de médias, profils, projets, pistes) ;
- `profiles` : profils dédiés aux logiciels de montage (Premiere, Resolve, Final Cut…) ;
- `structure` : création de l'arborescence d'un projet et mode « Préparer mon projet » ;
- `renaming` : renommage par lots avec modèles personnalisés ;
- `subtitles` : pistes disponibles, extraction de sous-titres et modèles .srt ;
- `scan` : inventaire des médias (sources, codecs, caractéristiques) et export CSV ;
- `store` : registre persistant des projets ;
- `workspace` : point d'entrée unique utilisé par l'interface.

Règles de sécurité appliquées partout :
- les fichiers d'origine ne sont JAMAIS déplacés, renommés, modifiés ou supprimés
  par l'organisation d'un projet : seules des copies sont créées ;
- aucune destination existante n'est écrasée sans confirmation explicite.
"""

from overload.creators.workspace import CreatorsWorkspace

__all__ = ["CreatorsWorkspace"]
