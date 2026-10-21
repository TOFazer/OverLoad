"""Fonctions communes : erreurs, chemins, journalisation."""

from overload.core.errors import OverloadError
from overload.core.paths import app_data_dir, library_db_path, settings_path

__all__ = ["OverloadError", "app_data_dir", "library_db_path", "settings_path"]
