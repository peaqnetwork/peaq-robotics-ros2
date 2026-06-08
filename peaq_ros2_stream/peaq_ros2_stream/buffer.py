"""Bounded SQLite buffer for signed Stream envelopes."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import hashlib
from dataclasses import dataclass
from typing import Any

from .transform import stable_json


@dataclass(frozen=True)
class BufferedEvent:
    id: str
    envelope: dict[str, Any]
    attempts: int
    created_at: float
    next_retry_at: float


class StreamEventBuffer:
    def __init__(
        self,
        path: str,
        max_events: int = 1000,
        retention_seconds: int = 86400,
        retry_interval_seconds: int = 30,
        overflow: str = 'drop_oldest',
    ) -> None:
        self.path = os.path.expanduser(path)
        self.max_events = max(1, int(max_events))
        self.retention_seconds = max(0, int(retention_seconds))
        self.retry_interval_seconds = max(1, int(retry_interval_seconds))
        self.overflow = 'pause' if overflow == 'pause' else 'drop_oldest'
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                '''
                CREATE TABLE IF NOT EXISTS stream_events (
                    id TEXT PRIMARY KEY,
                    envelope_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    next_retry_at REAL NOT NULL
                )
                '''
            )
            db.execute('CREATE INDEX IF NOT EXISTS stream_events_due_idx ON stream_events (next_retry_at, created_at)')

    def _count(self, db: sqlite3.Connection) -> int:
        row = db.execute('SELECT COUNT(*) FROM stream_events').fetchone()
        return int(row[0] if row else 0)

    def _prune_locked(self, db: sqlite3.Connection, now: float) -> None:
        if self.retention_seconds > 0:
            db.execute('DELETE FROM stream_events WHERE created_at < ?', (now - self.retention_seconds,))
        count = self._count(db)
        if count < self.max_events:
            return
        if self.overflow == 'pause':
            raise OverflowError('stream event buffer is full')
        overflow_count = count - self.max_events + 1
        db.execute(
            '''
            DELETE FROM stream_events
            WHERE id IN (
                SELECT id FROM stream_events ORDER BY created_at ASC LIMIT ?
            )
            ''',
            (overflow_count,),
        )

    def enqueue(self, envelope: dict[str, Any], now: float | None = None) -> str:
        observed = time.time() if now is None else now
        event_id = envelope_id(envelope)
        with self._connect() as db:
            self._prune_locked(db, observed)
            db.execute(
                '''
                INSERT OR IGNORE INTO stream_events (id, envelope_json, attempts, created_at, next_retry_at)
                VALUES (?, ?, 0, ?, ?)
                ''',
                (event_id, json.dumps(envelope, separators=(',', ':')), observed, observed),
            )
        return event_id

    def due(self, now: float | None = None, limit: int = 50) -> list[BufferedEvent]:
        observed = time.time() if now is None else now
        with self._connect() as db:
            rows = db.execute(
                '''
                SELECT id, envelope_json, attempts, created_at, next_retry_at
                FROM stream_events
                WHERE next_retry_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                ''',
                (observed, max(1, int(limit))),
            ).fetchall()
        return [
            BufferedEvent(
                id=str(row[0]),
                envelope=json.loads(row[1]),
                attempts=int(row[2]),
                created_at=float(row[3]),
                next_retry_at=float(row[4]),
            )
            for row in rows
        ]

    def mark_sent(self, event_id: str) -> None:
        with self._connect() as db:
            db.execute('DELETE FROM stream_events WHERE id = ?', (event_id,))

    def record_failure(self, event_id: str, now: float | None = None) -> None:
        observed = time.time() if now is None else now
        with self._connect() as db:
            db.execute(
                '''
                UPDATE stream_events
                SET attempts = attempts + 1,
                    next_retry_at = ?
                WHERE id = ?
                ''',
                (observed + self.retry_interval_seconds, event_id),
            )

    def prune(self, now: float | None = None) -> None:
        observed = time.time() if now is None else now
        with self._connect() as db:
            self._prune_locked(db, observed)

    def all_ids(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute('SELECT id FROM stream_events ORDER BY created_at ASC').fetchall()
        return [str(row[0]) for row in rows]


def envelope_id(envelope: dict[str, Any]) -> str:
    return hashlib.sha256(stable_json(envelope).encode('utf8')).hexdigest()


def flush_due(buffer: StreamEventBuffer, sender, now: float | None = None, limit: int = 50) -> tuple[int, int]:
    sent = 0
    failed = 0
    for event in buffer.due(now=now, limit=limit):
        try:
            sender(event.envelope)
            buffer.mark_sent(event.id)
            sent += 1
        except Exception:
            buffer.record_failure(event.id, now=now)
            failed += 1
    return sent, failed
