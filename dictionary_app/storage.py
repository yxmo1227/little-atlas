"""Private, per-user SQLite storage for dictionary entries and their images.

The application database is intentionally kept outside the source checkout.  A
fresh copy of the app therefore opens with an empty dictionary, even when the
app itself is distributed through GitHub.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys


APP_DIR_NAME = "PersonalDictionary"
DB_FILENAME = "dictionary.sqlite3"


def get_app_data_dir() -> Path:
    """Return this user's writable data directory, including in a frozen exe."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / APP_DIR_NAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True, slots=True)
class Entry:
    id: int | None = None
    title: str = ""
    original_input: str = ""
    category: str = ""
    subcategory: str = ""
    body_html: str = ""
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class ImageRecord:
    id: int
    entry_id: int
    local_path: str
    source_url: str = ""
    attribution: str = ""
    license: str = ""
    caption: str = ""
    sort_order: int = 0


class DictionaryStore:
    """Short-lived connection store safe to call from different UI threads.

    ``local_path`` in image records identifies a file managed by the caller.
    Deleting its record does not delete that file; callers can remove their
    own downloaded image after the record has been deleted.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else get_app_data_dir() / DB_FILENAME
        self.data_dir = self.db_path.parent
        self.images_dir = self.data_dir / "images"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    original_input TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    subcategory TEXT NOT NULL DEFAULT '',
                    body_html TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    local_path TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    attribution TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_entries_catalog
                    ON entries(category COLLATE NOCASE, subcategory COLLATE NOCASE,
                               title COLLATE NOCASE, id);
                CREATE INDEX IF NOT EXISTS idx_images_entry_order
                    ON images(entry_id, sort_order, id);
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(**dict(row))

    @staticmethod
    def _image(row: sqlite3.Row) -> ImageRecord:
        return ImageRecord(**dict(row))

    def upsert_entry(self, entry: Entry) -> Entry:
        """Insert a new entry or update an existing one, returning saved data.

        An ID that is absent from this dictionary raises ``KeyError`` so a
        stale edit cannot quietly create a second entry.
        """
        title = entry.title.strip()
        if not title:
            raise ValueError("Entry title cannot be empty")
        now = _utc_now()
        with self._connect() as connection:
            if entry.id is None:
                created_at = entry.created_at or now
                updated_at = entry.updated_at or now
                cursor = connection.execute(
                    """INSERT INTO entries
                       (title, original_input, category, subcategory, body_html,
                        source_url, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (title, entry.original_input, entry.category,
                     entry.subcategory, entry.body_html, entry.source_url,
                     created_at, updated_at),
                )
                entry_id = cursor.lastrowid
            else:
                cursor = connection.execute(
                    """UPDATE entries SET title = ?, original_input = ?,
                       category = ?, subcategory = ?, body_html = ?,
                       source_url = ?, updated_at = ? WHERE id = ?""",
                    (title, entry.original_input, entry.category,
                     entry.subcategory, entry.body_html, entry.source_url,
                     now, entry.id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Entry {entry.id} does not exist")
                entry_id = entry.id
            row = connection.execute(
                "SELECT * FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            assert row is not None
            return self._entry(row)

    def get_entry(self, entry_id: int) -> Entry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            return self._entry(row) if row is not None else None

    def list_entries(
        self,
        category: str | None = None,
        subcategory: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Entry]:
        """Return a predictable, alphabetical catalog order."""
        if offset < 0 or limit is not None and limit < 0:
            raise ValueError("limit and offset must be non-negative")
        conditions: list[str] = []
        parameters: list[str | int] = []
        if category is not None:
            conditions.append("category = ? COLLATE NOCASE")
            parameters.append(category)
        if subcategory is not None:
            conditions.append("subcategory = ? COLLATE NOCASE")
            parameters.append(subcategory)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        sql = (
            "SELECT * FROM entries" + where +
            " ORDER BY category COLLATE NOCASE, subcategory COLLATE NOCASE, "
            "title COLLATE NOCASE, id"
        )
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            parameters.extend([limit, offset])
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            parameters.append(offset)
        with self._connect() as connection:
            return [self._entry(row) for row in connection.execute(sql, parameters)]

    def search_entries(self, query: str, limit: int = 50) -> list[Entry]:
        """Find text locally; literal percent and underscore are not wildcards."""
        if limit < 0:
            raise ValueError("limit must be non-negative")
        pattern = "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM entries WHERE
                   title LIKE ? ESCAPE '\\' OR
                   original_input LIKE ? ESCAPE '\\' OR
                   category LIKE ? ESCAPE '\\' OR
                   subcategory LIKE ? ESCAPE '\\' OR
                   body_html LIKE ? ESCAPE '\\'
                   ORDER BY category COLLATE NOCASE, subcategory COLLATE NOCASE,
                            title COLLATE NOCASE, id LIMIT ?""",
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
            return [self._entry(row) for row in rows]

    def delete_entry(self, entry_id: int) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "DELETE FROM entries WHERE id = ?", (entry_id,)
            ).rowcount == 1

    def add_image(
        self,
        entry_id: int,
        local_path: str | Path,
        source_url: str = "",
        attribution: str = "",
        license: str = "",
        caption: str = "",
        sort_order: int | None = None,
    ) -> ImageRecord:
        if not str(local_path).strip():
            raise ValueError("Image local_path cannot be empty")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM entries WHERE id = ?", (entry_id,)
            ).fetchone() is None:
                raise KeyError(f"Entry {entry_id} does not exist")
            if sort_order is None:
                sort_order = connection.execute(
                    "SELECT COALESCE(MAX(sort_order) + 1, 0) FROM images WHERE entry_id = ?",
                    (entry_id,),
                ).fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO images
                   (entry_id, local_path, source_url, attribution, license,
                    caption, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, str(local_path), source_url, attribution, license,
                 caption, sort_order),
            )
            row = connection.execute(
                "SELECT * FROM images WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            assert row is not None
            return self._image(row)

    def list_images(self, entry_id: int) -> list[ImageRecord]:
        with self._connect() as connection:
            return [self._image(row) for row in connection.execute(
                "SELECT * FROM images WHERE entry_id = ? ORDER BY sort_order, id",
                (entry_id,),
            )]

    def delete_image(self, image_id: int) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "DELETE FROM images WHERE id = ?", (image_id,)
            ).rowcount == 1
