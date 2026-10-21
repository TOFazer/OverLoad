"""Stockage SQLite versionné de l'historique des téléchargements.

Conformément aux règles d'OverLoad :
- la suppression ou la purge d'entrées d'historique ne supprime JAMAIS
  les fichiers téléchargés sur le disque ;
- le schéma est versionné dans `schema_meta` pour permettre des migrations sûres.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes, format_duration, format_speed

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HistoryEntry:
    """Entrée immuable représentant un téléchargement passé."""

    id: str
    task_id: str
    url: str
    filename: str
    destination_path: str
    destination_dir: str
    status: str
    size_bytes: int
    average_speed_bps: float
    duration_seconds: float
    retries_used: int
    issues_count: int
    error_message: str
    started_at: str
    finished_at: str

    @property
    def file_exists(self) -> bool:
        return Path(self.destination_path).is_file()

    @property
    def dir_exists(self) -> bool:
        return Path(self.destination_dir).is_dir()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "url": self.url,
            "filename": self.filename,
            "destination_path": self.destination_path,
            "destination_dir": self.destination_dir,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "size_human": format_bytes(self.size_bytes),
            "average_speed_bps": round(self.average_speed_bps, 2),
            "average_speed_human": format_speed(self.average_speed_bps),
            "duration_seconds": round(self.duration_seconds, 2),
            "duration_human": format_duration(self.duration_seconds),
            "retries_used": self.retries_used,
            "issues_count": self.issues_count,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "file_exists": self.file_exists,
            "dir_exists": self.dir_exists,
        }


class DownloadHistoryStore:
    """Journal SQLite thread-safe des téléchargements terminés, échoués ou annulés."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS download_history (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    destination_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    average_speed_bps REAL NOT NULL DEFAULT 0.0,
                    duration_seconds REAL NOT NULL DEFAULT 0.0,
                    retries_used INTEGER NOT NULL DEFAULT 0,
                    issues_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_finished "
                "ON download_history(finished_at DESC)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_url ON download_history(url)"
            )

    def record(
        self,
        *,
        task_id: str,
        url: str,
        filename: str,
        destination_path: Path | str,
        status: str,
        size_bytes: int = 0,
        average_speed_bps: float = 0.0,
        duration_seconds: float = 0.0,
        retries_used: int = 0,
        issues_count: int = 0,
        error_message: str = "",
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> HistoryEntry:
        now_iso = datetime.now(UTC).isoformat()
        dest = Path(destination_path)
        entry = HistoryEntry(
            id=uuid.uuid4().hex[:12],
            task_id=task_id,
            url=url,
            filename=filename,
            destination_path=str(dest),
            destination_dir=str(dest.parent),
            status=status,
            size_bytes=max(0, int(size_bytes)),
            average_speed_bps=max(0.0, float(average_speed_bps)),
            duration_seconds=max(0.0, float(duration_seconds)),
            retries_used=max(0, int(retries_used)),
            issues_count=max(0, int(issues_count)),
            error_message=error_message,
            started_at=started_at or now_iso,
            finished_at=finished_at or now_iso,
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO download_history (
                    id, task_id, url, filename, destination_path, destination_dir,
                    status, size_bytes, average_speed_bps, duration_seconds,
                    retries_used, issues_count, error_message, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.task_id,
                    entry.url,
                    entry.filename,
                    entry.destination_path,
                    entry.destination_dir,
                    entry.status,
                    entry.size_bytes,
                    entry.average_speed_bps,
                    entry.duration_seconds,
                    entry.retries_used,
                    entry.issues_count,
                    entry.error_message,
                    entry.started_at,
                    entry.finished_at,
                ),
            )
        return entry

    def get_entry(self, entry_id: str) -> HistoryEntry:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM download_history WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if row is None:
            raise OverloadError(
                "Entrée d'historique introuvable.",
                f"identifiant « {entry_id} » inconnu.",
                "Rafraîchissez l'historique.",
            )
        return self._row_to_entry(row)

    def list_entries(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 200,
    ) -> list[HistoryEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if status and status != "all":
            clauses.append("status = ?")
            params.append(status)
        if query and query.strip():
            needle = f"%{query.strip()}%"
            clauses.append("(filename LIKE ? OR url LIKE ?)")
            params.extend([needle, needle])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 1000)))
        sql = (
            f"SELECT * FROM download_history {where} "
            "ORDER BY finished_at DESC, rowid DESC LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def find_completed_by_url(self, url: str) -> HistoryEntry | None:
        """Retourne le dernier téléchargement réussi pour cette URL toujours présent sur disque."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM download_history
                WHERE url = ? AND status = 'completed'
                ORDER BY finished_at DESC, rowid DESC
                """,
                (url.strip(),),
            ).fetchall()
        for row in rows:
            entry = self._row_to_entry(row)
            if entry.file_exists:
                return entry
        return None

    def remove_entry(self, entry_id: str) -> bool:
        """Retire une entrée de l'historique sans toucher au fichier sur le disque."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM download_history WHERE id = ?",
                (entry_id,),
            )
            return cur.rowcount > 0

    def clear(self) -> int:
        """Vide l'historique sans jamais supprimer les fichiers téléchargés."""
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM download_history")
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> DownloadHistoryStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
        return HistoryEntry(
            id=row["id"],
            task_id=row["task_id"],
            url=row["url"],
            filename=row["filename"],
            destination_path=row["destination_path"],
            destination_dir=row["destination_dir"],
            status=row["status"],
            size_bytes=row["size_bytes"],
            average_speed_bps=row["average_speed_bps"],
            duration_seconds=row["duration_seconds"],
            retries_used=row["retries_used"],
            issues_count=row["issues_count"],
            error_message=row["error_message"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
