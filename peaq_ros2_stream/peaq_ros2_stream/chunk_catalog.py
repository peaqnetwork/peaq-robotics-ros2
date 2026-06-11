"""SQLite catalog for locally produced Stream chunks."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .envelope import utc_now_iso


@dataclass(frozen=True)
class ChunkCatalogRecord:
    chunk_id: str
    previous_chunk_id: str
    chunk_index: int
    machine_id: str
    agent_id: str
    topic: str
    message_type: str
    policy_id: str
    policy_version: int
    sequence_number: int
    source_timestamp: str
    agent_received_at: str
    observed_at: str
    encrypted_data_hash: str
    plaintext_hash: str
    storage_ref: str
    storage_provider: str
    local_path: str
    manifest_path: str
    size_bytes: int
    status: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamChunkCatalog:
    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                '''
                CREATE TABLE IF NOT EXISTS stream_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    previous_chunk_id TEXT NOT NULL DEFAULT '',
                    chunk_index INTEGER NOT NULL,
                    machine_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_version INTEGER NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    source_timestamp TEXT NOT NULL DEFAULT '',
                    agent_received_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    encrypted_data_hash TEXT NOT NULL,
                    plaintext_hash TEXT NOT NULL,
                    storage_ref TEXT NOT NULL,
                    storage_provider TEXT NOT NULL,
                    local_path TEXT NOT NULL DEFAULT '',
                    manifest_path TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                '''
            )
            db.execute(
                '''
                CREATE INDEX IF NOT EXISTS stream_chunks_machine_topic_time_idx
                ON stream_chunks (machine_id, topic, observed_at, chunk_index)
                '''
            )
            db.execute(
                '''
                CREATE INDEX IF NOT EXISTS stream_chunks_status_time_idx
                ON stream_chunks (status, observed_at)
                '''
            )

    def upsert(self, record: ChunkCatalogRecord) -> None:
        values = record.to_dict()
        columns = list(values.keys())
        placeholders = ', '.join(['?'] * len(columns))
        assignments = ', '.join(
            f'{column} = excluded.{column}'
            for column in columns
            if column not in {'chunk_id', 'created_at'}
        )
        with self._connect() as db:
            db.execute(
                f'''
                INSERT INTO stream_chunks ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(chunk_id) DO UPDATE SET {assignments}
                ''',
                tuple(values[column] for column in columns),
            )

    def get(self, chunk_id: str) -> ChunkCatalogRecord | None:
        with self._connect() as db:
            row = db.execute('SELECT * FROM stream_chunks WHERE chunk_id = ?', (chunk_id,)).fetchone()
        return _row_to_record(row) if row else None

    def list_chunks(
        self,
        machine_id: str = '',
        topic: str = '',
        start_time: str = '',
        end_time: str = '',
        status: str = '',
        limit: int = 100,
    ) -> list[ChunkCatalogRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        if machine_id:
            clauses.append('machine_id = ?')
            values.append(machine_id)
        if topic:
            clauses.append('topic = ?')
            values.append(topic)
        if start_time:
            clauses.append('observed_at >= ?')
            values.append(start_time)
        if end_time:
            clauses.append('observed_at <= ?')
            values.append(end_time)
        if status:
            clauses.append('status = ?')
            values.append(status)

        where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
        values.append(max(1, int(limit)))
        with self._connect() as db:
            rows = db.execute(
                f'''
                SELECT * FROM stream_chunks
                {where}
                ORDER BY observed_at ASC, chunk_index ASC
                LIMIT ?
                ''',
                tuple(values),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def update_storage(self, chunk_id: str, storage_ref: str, status: str = 'stored') -> None:
        parsed = urlparse(storage_ref)
        provider = parsed.scheme or 'local'
        local_path = _local_path_from_ref(storage_ref)
        size_bytes = _path_size(local_path)
        with self._connect() as db:
            db.execute(
                '''
                UPDATE stream_chunks
                SET storage_ref = ?,
                    storage_provider = ?,
                    local_path = ?,
                    size_bytes = ?,
                    status = ?,
                    updated_at = ?
                WHERE chunk_id = ?
                ''',
                (storage_ref, provider, local_path, size_bytes, status, utc_now_iso(), chunk_id),
            )


def record_from_manifest(
    manifest: dict[str, Any],
    *,
    machine_id: str,
    agent_id: str,
    topic: str,
    message_type: str,
    policy_id: str,
    policy_version: int,
    sequence_number: int,
    source_timestamp: str | None,
    agent_received_at: str,
    manifest_path: str,
    local_path: str = '',
    storage_provider: str = '',
    status: str = 'local',
) -> ChunkCatalogRecord:
    storage_ref = str(manifest['storageRef'])
    resolved_local_path = local_path or _local_path_from_ref(storage_ref)
    created_at = utc_now_iso()
    observed_at = source_timestamp or agent_received_at or created_at
    return ChunkCatalogRecord(
        chunk_id=str(manifest['chunkId']),
        previous_chunk_id=str(manifest.get('previousChunkId') or ''),
        chunk_index=int(manifest['index']),
        machine_id=machine_id,
        agent_id=agent_id,
        topic=topic,
        message_type=message_type,
        policy_id=policy_id,
        policy_version=int(policy_version),
        sequence_number=int(sequence_number),
        source_timestamp=str(source_timestamp or ''),
        agent_received_at=agent_received_at,
        observed_at=observed_at,
        encrypted_data_hash=str(manifest['encryptedDataHash']),
        plaintext_hash=str(manifest['plaintextHash']),
        storage_ref=storage_ref,
        storage_provider=storage_provider or urlparse(storage_ref).scheme or 'local',
        local_path=resolved_local_path,
        manifest_path=str(Path(manifest_path).expanduser()),
        size_bytes=_path_size(resolved_local_path),
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


def _row_to_record(row: sqlite3.Row) -> ChunkCatalogRecord:
    data = dict(row)
    return ChunkCatalogRecord(
        chunk_id=str(data['chunk_id']),
        previous_chunk_id=str(data['previous_chunk_id']),
        chunk_index=int(data['chunk_index']),
        machine_id=str(data['machine_id']),
        agent_id=str(data['agent_id']),
        topic=str(data['topic']),
        message_type=str(data['message_type']),
        policy_id=str(data['policy_id']),
        policy_version=int(data['policy_version']),
        sequence_number=int(data['sequence_number']),
        source_timestamp=str(data['source_timestamp']),
        agent_received_at=str(data['agent_received_at']),
        observed_at=str(data['observed_at']),
        encrypted_data_hash=str(data['encrypted_data_hash']),
        plaintext_hash=str(data['plaintext_hash']),
        storage_ref=str(data['storage_ref']),
        storage_provider=str(data['storage_provider']),
        local_path=str(data['local_path']),
        manifest_path=str(data['manifest_path']),
        size_bytes=int(data['size_bytes']),
        status=str(data['status']),
        created_at=str(data['created_at']),
        updated_at=str(data['updated_at']),
    )


def _local_path_from_ref(storage_ref: str) -> str:
    parsed = urlparse(storage_ref)
    if parsed.scheme != 'file':
        return ''
    return unquote(parsed.path)


def _path_size(path: str) -> int:
    if not path:
        return 0
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0
