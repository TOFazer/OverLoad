"""Journal technique avec rotation, dans le dossier de données (pas de console)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "overload.log"
_HANDLER_MARK = "_overload_file_handler"


def setup_logging(logs_directory: Path, level: int = logging.INFO) -> Path:
    logs_directory.mkdir(parents=True, exist_ok=True)
    path = logs_directory / LOG_FILE_NAME
    root = logging.getLogger()
    if any(getattr(h, _HANDLER_MARK, False) for h in root.handlers):
        return path
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s"))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)
    return path
