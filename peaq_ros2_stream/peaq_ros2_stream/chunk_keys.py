"""Local per-chunk key cache for buyer access wrapping."""

from __future__ import annotations

import os
import sqlite3


class StreamChunkKeyStore:
    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                '''
                CREATE TABLE IF NOT EXISTS stream_chunk_keys (
                    chunk_id TEXT PRIMARY KEY,
                    key_hex TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )

    def put(self, chunk_id: str, key_hex: str) -> None:
        clean_key = key_hex.removeprefix('0x').lower()
        if len(clean_key) != 64 or any(char not in '0123456789abcdef' for char in clean_key):
            raise ValueError('chunk key must be a 32-byte hex string')
        with self._connect() as db:
            db.execute(
                '''
                INSERT INTO stream_chunk_keys (chunk_id, key_hex)
                VALUES (?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    key_hex = excluded.key_hex,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (chunk_id, clean_key),
            )

    def get(self, chunk_id: str) -> str:
        with self._connect() as db:
            row = db.execute('SELECT key_hex FROM stream_chunk_keys WHERE chunk_id = ?', (chunk_id,)).fetchone()
        return str(row[0]) if row else ''

    def delete(self, chunk_id: str) -> None:
        with self._connect() as db:
            db.execute('DELETE FROM stream_chunk_keys WHERE chunk_id = ?', (chunk_id,))
