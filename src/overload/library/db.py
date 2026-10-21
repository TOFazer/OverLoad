"""Persistance SQLite de la bibliothèque.

- Une seule base : ``library.db`` dans le dossier de données OverLoad.
- Schéma versionné (user_version) avec migrations automatiques.
- Recherche, filtres et tri pour retrouver un fichier des mois plus tard.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from overload.library.models import MediaEntry, MediaType

SCHEMA_VERSION = 1

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS media_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT UNIQUE NOT NULL,
    filename        TEXT NOT NULL,
    media_type      TEXT NOT NULL,
    extension       TEXT NOT NULL,
    size            INTEGER NOT NULL,
    mtime           REAL NOT NULL,
    ctime           REAL,
    duration        REAL,
    width           INTEGER,
    height          INTEGER,
    hash            TEXT,
    hash_partial    TEXT,
    thumbnail_path  TEXT,
    source_url      TEXT,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_type ON media_entries(media_type);
CREATE INDEX IF NOT EXISTS idx_media_size ON media_entries(size);
CREATE INDEX IF NOT EXISTS idx_media_mtime ON media_entries(mtime);
CREATE INDEX IF NOT EXISTS idx_media_hash ON media_entries(hash);
CREATE INDEX IF NOT EXISTS idx_media_filename ON media_entries(filename);
CREATE INDEX IF NOT EXISTS idx_media_extension ON media_entries(extension);
"""


class LibraryStore:
    """Wrapper SQLite : création, insertion, recherche et doublons."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_CREATE_SQL)
        # user_version pour de futures migrations
        cur = self._conn.execute("PRAGMA user_version;")
        ver = cur.fetchone()[0]
        if ver < SCHEMA_VERSION:
            self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION};")
            self._conn.commit()

    # ------------------------------------------------------------------ CRUD
    def upsert_entry(self, entry: MediaEntry) -> MediaEntry:
        """Insère ou met à jour une entrée d'après son chemin."""
        now = time.time() if entry.created_at is None else entry.created_at
        self._conn.execute(
            """
            INSERT INTO media_entries
                (path, filename, media_type, extension, size, mtime, ctime,
                 duration, width, height, hash, hash_partial, thumbnail_path, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                filename=excluded.filename,
                media_type=excluded.media_type,
                extension=excluded.extension,
                size=excluded.size,
                mtime=excluded.mtime,
                ctime=excluded.ctime,
                duration=excluded.duration,
                width=excluded.width,
                height=excluded.height,
                hash=excluded.hash,
                hash_partial=excluded.hash_partial,
                thumbnail_path=excluded.thumbnail_path,
                source_url=excluded.source_url
            """,
            (
                str(entry.path.resolve()) if not entry.path.is_absolute() else str(entry.path),
                entry.filename,
                entry.media_type.value,
                entry.extension,
                entry.size,
                entry.mtime,
                entry.ctime,
                entry.duration,
                entry.width,
                entry.height,
                entry.hash,
                entry.hash_partial,
                str(entry.thumbnail_path) if entry.thumbnail_path else None,
                entry.source_url,
                now,
            ),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT id FROM media_entries WHERE path=?", (str(entry.path),)).fetchone()
        # Cas où path résolu diffère — on récupère via filename+size+mtime ?
        if row is None:
            row = self._conn.execute(
                "SELECT id FROM media_entries WHERE path=?", (str(entry.path.resolve()),)
            ).fetchone()
        if row:
            entry.id = row["id"]
            entry.created_at = now
        return entry

    def remove_entry(self, path: Path) -> bool:
        cur = self._conn.execute("DELETE FROM media_entries WHERE path=?", (str(path),))
        # aussi essayer chemin résolu
        if cur.rowcount == 0:
            cur = self._conn.execute("DELETE FROM media_entries WHERE path=?", (str(path.resolve()),))
        self._conn.commit()
        return cur.rowcount > 0

    def remove_missing(self) -> int:
        """Supprime de l'index les fichiers qui n'existent plus sur disque."""
        rows = self._conn.execute("SELECT id, path FROM media_entries").fetchall()
        missing_ids = [r["id"] for r in rows if not Path(r["path"]).exists()]
        if missing_ids:
            self._conn.executemany("DELETE FROM media_entries WHERE id=?", [(i,) for i in missing_ids])
            self._conn.commit()
        return len(missing_ids)

    def get_by_path(self, path: Path) -> MediaEntry | None:
        row = self._conn.execute("SELECT * FROM media_entries WHERE path=?", (str(path),)).fetchone()
        if row is None:
            row = self._conn.execute("SELECT * FROM media_entries WHERE path=?", (str(path.resolve()),)).fetchone()
        return _row_to_entry(row) if row else None

    def get_by_id(self, entry_id: int) -> MediaEntry | None:
        row = self._conn.execute("SELECT * FROM media_entries WHERE id=?", (entry_id,)).fetchone()
        return _row_to_entry(row) if row else None

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM media_entries").fetchone()[0]

    def all_entries(self) -> list[MediaEntry]:
        rows = self._conn.execute("SELECT * FROM media_entries ORDER BY mtime DESC").fetchall()
        return [_row_to_entry(r) for r in rows]

    # ----------------------------------------------------------- Recherche / filtres
    def search(
        self,
        query: str | None = None,
        media_types: list[MediaType | str] | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        after: float | None = None,
        before: float | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        extension: str | None = None,
        order_by: str = "mtime",
        descending: bool = True,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MediaEntry]:
        """Requête combinée : texte + filtres.

        - ``query`` : recherche insensible à la casse dans filename et path.
        - ``after`` / ``before`` : timestamps mtime.
        - ``order_by`` : colonne autorisée (mtime, size, filename, duration, media_type).
        """
        allowed_order = {"mtime", "size", "filename", "duration", "media_type", "extension", "created_at"}
        if order_by not in allowed_order:
            order_by = "mtime"

        where: list[str] = []
        params: list[object] = []

        if query:
            where.append("(LOWER(filename) LIKE ? OR LOWER(path) LIKE ?)")
            like = f"%{query.lower()}%"
            params.extend([like, like])

        if media_types:
            vals = [m.value if isinstance(m, MediaType) else str(m) for m in media_types]
            placeholders = ",".join("?" for _ in vals)
            where.append(f"media_type IN ({placeholders})")
            params.extend(vals)

        if extension:
            where.append("LOWER(extension)=LOWER(?)")
            params.append(extension)

        if min_size is not None:
            where.append("size >= ?")
            params.append(min_size)
        if max_size is not None:
            where.append("size <= ?")
            params.append(max_size)
        if after is not None:
            where.append("mtime >= ?")
            params.append(after)
        if before is not None:
            where.append("mtime <= ?")
            params.append(before)
        if min_duration is not None:
            where.append("duration >= ?")
            params.append(min_duration)
        if max_duration is not None:
            where.append("duration <= ?")
            params.append(max_duration)

        sql = "SELECT * FROM media_entries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order_by} {'DESC' if descending else 'ASC'}"
        # Pour retrouver un fichier de plusieurs mois, trier par mtime DESC met les récents d'abord.
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)

        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def distinct_extensions(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT extension FROM media_entries ORDER BY extension").fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict:
        """Statistiques rapides pour le tableau de bord."""
        total = self.count()
        by_type = {}
        for row in self._conn.execute("SELECT media_type, COUNT(*), SUM(size) FROM media_entries GROUP BY media_type"):
            by_type[row[0]] = {"count": row[1], "bytes": row[2] or 0}
        total_size = self._conn.execute("SELECT SUM(size) FROM media_entries").fetchone()[0] or 0
        return {"total": total, "total_bytes": total_size, "by_type": by_type}

    def close(self) -> None:
        self._conn.close()


def _row_to_entry(row: sqlite3.Row) -> MediaEntry:
    return MediaEntry(
        id=row["id"],
        path=Path(row["path"]),
        filename=row["filename"],
        media_type=MediaType(row["media_type"]),
        extension=row["extension"],
        size=row["size"],
        mtime=row["mtime"],
        ctime=row["ctime"],
        duration=row["duration"],
        width=row["width"],
        height=row["height"],
        hash=row["hash"],
        hash_partial=row["hash_partial"],
        thumbnail_path=Path(row["thumbnail_path"]) if row["thumbnail_path"] else None,
        source_url=row["source_url"],
        created_at=row["created_at"],
    )
