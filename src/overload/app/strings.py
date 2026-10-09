"""Textes de l'interface, centralisés pour la traduction (français pour l'instant)."""

from __future__ import annotations

APP_TITLE = "OverLoad"

NAV = {
    "home": "Accueil",
    "downloads": "Téléchargements",
    "settings": "Paramètres",
    "help": "Aide",
}

STATE_LABELS = {
    "queued": "En attente",
    "running": "En cours",
    "paused": "En pause",
    "finalizing": "Vérification",
    "completed": "Terminé",
    "failed": "Échec",
    "cancelled": "Annulé",
}

HOME_TITLE = "Télécharger un fichier"
HOME_SUBTITLE = (
    "Collez l'adresse directe d'un fichier (commençant par https:// ou http://). "
    "OverLoad refuse les adresses locales et les protocoles non pris en charge."
)
URL_PLACEHOLDER = "https://exemple.com/video.mp4"
BTN_DOWNLOAD = "Télécharger"
MSG_ADDED = "Téléchargement ajouté. Suivez-le dans la section Téléchargements."
MSG_EMPTY_URL = "Erreur : collez une adresse avant de lancer le téléchargement."
RECENT_TITLE = "Tâches récentes"
RECENT_EMPTY = "Aucun téléchargement pour l'instant."
BTN_SHOW_DOWNLOADS = "Voir les téléchargements"
BTN_OPEN_FOLDER = "Ouvrir le dossier de téléchargement"
DISK_LABEL = "Espace disponible dans « {folder} » : {free}"
DISK_UNKNOWN = "Espace disque : indisponible pour ce dossier."

DOWNLOADS_TITLE = "Téléchargements"
COLUMNS = ["Nom", "Source", "État", "Progression", "Vitesse", "Temps restant", "Dossier"]
BTN_PAUSE = "Mettre en pause"
BTN_RESUME = "Reprendre"
BTN_CANCEL = "Annuler"
BTN_RETRY = "Relancer"
BTN_OPEN_FILE = "Ouvrir le fichier"
BTN_REVEAL = "Révéler"
TIP_REVEAL = "Affiche le fichier dans l'Explorateur Windows"
BTN_OPEN_DIR = "Ouvrir le dossier"
BTN_COPY_PATH = "Copier le chemin"
DETAILS_NONE = "Sélectionnez une tâche pour voir ses détails."
DETAILS_ERROR_PREFIX = "Problème : "
DETAILS_PATH_PREFIX = "Emplacement : "
DOWNLOADS_EMPTY = "Aucun téléchargement. Ajoutez une adresse depuis la page d'accueil."
ACTION_ERROR_TITLE = "Action impossible"
COPIED = "Chemin copié dans le presse-papiers."

SETTINGS_TITLE = "Paramètres"
SETTINGS_FOLDER = "Dossier de téléchargement"
BTN_BROWSE = "Parcourir…"
SETTINGS_PARALLEL = "Téléchargements simultanés"
SETTINGS_PARALLEL_HELP = "Appliqué au prochain démarrage de l'application."
SETTINGS_THEME = "Thème"
THEME_LABELS = {"system": "Suivre Windows", "light": "Clair", "dark": "Sombre"}
SETTINGS_STORAGE = "Données de l'application"
SETTINGS_DATA = "Réglages et données : {path}"
SETTINGS_LOGS = "Journaux techniques : {path}"
BTN_OPEN_LOGS = "Ouvrir le dossier des journaux"
BTN_SAVE = "Enregistrer"
SETTINGS_SAVED = "Paramètres enregistrés."
SETTINGS_BAD_FOLDER = "Erreur : le dossier de téléchargement est inaccessible ({error})."

HELP_TITLE = "Aide"
HELP_BODY = """
<h3>Sources prises en charge</h3>
<p>La version actuelle télécharge les adresses <b>directes</b> qui pointent vers un fichier
(https:// ou http://). OverLoad ne contourne pas les protections d'accès, les DRM ni les
restrictions d'une plateforme.</p>
<h3>Où sont mes fichiers ?</h3>
<p>Dans le dossier indiqué dans les paramètres. OverLoad ne remplace jamais un fichier existant :
il ajoute « (2) » au nom si nécessaire.</p>
<h3>Pause, reprise, annulation</h3>
<p>La pause conserve le fichier partiel. La reprise continue là où le téléchargement s'est arrêté.
L'annulation supprime le fichier partiel ; un fichier déjà terminé n'est jamais touché.</p>
<h3>Fichiers exécutables</h3>
<p>OverLoad n'ouvre pas les programmes et scripts (.exe, .bat, .msi…). Utilisez « Révéler »
pour les contrôler avant de les lancer.</p>
<h3>Signaler un problème</h3>
<p>Ouvrez le dossier des journaux depuis les paramètres et joignez le fichier
<i>overload.log</i> à votre signalement. Il ne contient pas le contenu de vos fichiers.</p>
"""
