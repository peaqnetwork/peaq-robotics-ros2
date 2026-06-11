"""Local HTTP delivery service for encrypted Stream chunks."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .chunk_catalog import StreamChunkCatalog
from .chunk_storage import read_manifest_array


class StreamDeliveryServer:
    def __init__(
        self,
        catalog: StreamChunkCatalog,
        manifest_path: str,
        token: str,
        host: str = '127.0.0.1',
        port: int = 8765,
    ) -> None:
        self.catalog = catalog
        self.manifest_path = manifest_path
        self.token = token
        self.host = host
        self.port = int(port)
        self._tokens: set[str] = {token} if token else set()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if not self._server:
            return self.host, self.port
        host, port = self._server.server_address
        return str(host), int(port)

    def start(self) -> None:
        if self._server:
            return
        handler = self._handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def allow_token(self, token: str) -> None:
        if token:
            self._tokens.add(token)

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _handler(self):
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                parts = [unquote(part) for part in parsed.path.strip('/').split('/') if part]

                if parsed.path == '/health':
                    self._json(200, {'ok': True})
                    return

                if not self._authorized():
                    self._json(401, {'error': 'unauthorized'})
                    return

                if parts == ['chunks']:
                    self._list_chunks(parsed.query)
                    return

                if len(parts) == 2 and parts[0] == 'chunks':
                    self._chunk_record(parts[1])
                    return

                if len(parts) == 3 and parts[0] == 'chunks' and parts[2] == 'manifest':
                    self._chunk_manifest(parts[1])
                    return

                if len(parts) == 3 and parts[0] == 'chunks' and parts[2] == 'data':
                    self._chunk_data(parts[1])
                    return

                self._json(404, {'error': 'not found'})

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _authorized(self) -> bool:
                header = self.headers.get('authorization', '')
                if not header.startswith('Bearer '):
                    return False
                return header.removeprefix('Bearer ').strip() in parent._tokens

            def _list_chunks(self, query_text: str) -> None:
                query = parse_qs(query_text)
                limit = _query_int(query, 'limit', 100)
                items = parent.catalog.list_chunks(
                    machine_id=_query_str(query, 'machineId'),
                    topic=_query_str(query, 'topic'),
                    start_time=_query_str(query, 'startTime'),
                    end_time=_query_str(query, 'endTime'),
                    status=_query_str(query, 'status'),
                    limit=limit,
                )
                self._json(200, {'items': [item.to_dict() for item in items], 'count': len(items)})

            def _chunk_record(self, chunk_id: str) -> None:
                record = parent.catalog.get(chunk_id)
                if not record:
                    self._json(404, {'error': 'chunk not found'})
                    return
                self._json(200, {'item': record.to_dict()})

            def _chunk_manifest(self, chunk_id: str) -> None:
                manifest = _find_manifest(parent.manifest_path, chunk_id)
                if not manifest:
                    self._json(404, {'error': 'chunk manifest not found'})
                    return
                self._json(200, {'item': manifest})

            def _chunk_data(self, chunk_id: str) -> None:
                record = parent.catalog.get(chunk_id)
                if not record:
                    self._json(404, {'error': 'chunk not found'})
                    return
                path = Path(record.local_path)
                if not record.local_path or not path.exists():
                    self._json(404, {'error': 'local chunk file not found', 'storageRef': record.storage_ref})
                    return
                data = path.read_bytes()
                start, end, partial = _byte_range(self.headers.get('range', ''), len(data))
                body = data[start : end + 1]
                self.send_response(206 if partial else 200)
                self.send_header('content-type', 'application/octet-stream')
                self.send_header('accept-ranges', 'bytes')
                self.send_header('content-length', str(len(body)))
                if partial:
                    self.send_header('content-range', f'bytes {start}-{end}/{len(data)}')
                self.send_header('x-stream-chunk-id', record.chunk_id)
                self.send_header('x-stream-encrypted-data-hash', record.encrypted_data_hash)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf8')
                self.send_response(status)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _find_manifest(manifest_path: str, chunk_id: str) -> dict[str, Any] | None:
    for manifest in read_manifest_array(manifest_path):
        if str(manifest.get('chunkId')) == chunk_id:
            return manifest
    return None


def _query_str(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0]).strip() if values else ''


def _query_int(query: dict[str, list[str]], key: str, fallback: int) -> int:
    try:
        return int(_query_str(query, key) or fallback)
    except ValueError:
        return fallback


def _byte_range(header: str, size: int) -> tuple[int, int, bool]:
    if not header.startswith('bytes=') or size <= 0:
        return 0, max(0, size - 1), False
    value = header.removeprefix('bytes=').split(',', 1)[0].strip()
    start_text, _, end_text = value.partition('-')
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        else:
            suffix = int(end_text)
            start = max(0, size - suffix)
            end = size - 1
    except ValueError:
        return 0, size - 1, False
    start = max(0, min(start, size - 1))
    end = max(start, min(end, size - 1))
    return start, end, True
