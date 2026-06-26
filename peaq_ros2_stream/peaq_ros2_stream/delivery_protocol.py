"""peaqOS Stream chunk request/response protocol."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from .delivery_transport import DeliveryAck, DeliveryChunk


CHUNK_PROTOCOL_ID = '/peaqos/stream/chunk/1.0.0'
CHUNK_PROTOCOL_ENCODING = 'peaqos-json-frame-v1'
MAX_FRAME_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ChunkRequest:
    purchase_id: str
    delivery_session_id: str
    buyer_id: str
    chunk_ids: list[str]
    request_id: str = field(default_factory=lambda: uuid4().hex)
    resume_offsets: dict[str, int] = field(default_factory=dict)


def encode_frame(frame: dict[str, Any]) -> bytes:
    payload = json.dumps(frame, separators=(',', ':'), sort_keys=True).encode('utf8')
    if len(payload) > MAX_FRAME_BYTES:
        raise ValueError('stream delivery frame is too large')
    return struct.pack('>I', len(payload)) + payload


def decode_frames(data: bytes) -> tuple[list[dict[str, Any]], bytes]:
    frames: list[dict[str, Any]] = []
    offset = 0
    while len(data) - offset >= 4:
        length = struct.unpack('>I', data[offset:offset + 4])[0]
        if length > MAX_FRAME_BYTES:
            raise ValueError('stream delivery frame is too large')
        frame_start = offset + 4
        frame_end = frame_start + length
        if len(data) < frame_end:
            break
        frame = json.loads(data[frame_start:frame_end].decode('utf8'))
        if not isinstance(frame, dict):
            raise ValueError('stream delivery frame must be a JSON object')
        frames.append(frame)
        offset = frame_end
    return frames, data[offset:]


def encode_frame_sequence(frames: list[dict[str, Any]]) -> bytes:
    return b''.join(encode_frame(frame) for frame in frames)


def decode_frame_sequence(data: bytes) -> list[dict[str, Any]]:
    frames, remainder = decode_frames(data)
    if remainder:
        raise ValueError('stream delivery frame sequence ended with partial data')
    return frames


def chunk_request_frame(request: ChunkRequest) -> dict[str, Any]:
    return {
        'type': 'chunk.request',
        'protocol': CHUNK_PROTOCOL_ID,
        'encoding': CHUNK_PROTOCOL_ENCODING,
        'requestId': request.request_id,
        'purchaseId': request.purchase_id,
        'deliverySessionId': request.delivery_session_id,
        'buyerId': request.buyer_id,
        'chunkIds': request.chunk_ids,
        'resumeOffsets': request.resume_offsets,
    }


def parse_chunk_request(frame: dict[str, Any]) -> ChunkRequest:
    if frame.get('type') != 'chunk.request':
        raise ValueError('first stream delivery frame must be chunk.request')
    if frame.get('protocol') != CHUNK_PROTOCOL_ID:
        raise ValueError('unsupported stream delivery protocol')
    chunk_ids = frame.get('chunkIds')
    if not isinstance(chunk_ids, list) or not all(isinstance(item, str) and item for item in chunk_ids):
        raise ValueError('chunk.request must include chunkIds')
    resume_offsets = frame.get('resumeOffsets')
    return ChunkRequest(
        purchase_id=str(frame.get('purchaseId') or ''),
        delivery_session_id=str(frame.get('deliverySessionId') or ''),
        buyer_id=str(frame.get('buyerId') or ''),
        chunk_ids=chunk_ids,
        request_id=str(frame.get('requestId') or uuid4().hex),
        resume_offsets=resume_offsets if isinstance(resume_offsets, dict) else {},
    )


def chunk_manifest_frame(request: ChunkRequest, chunk: DeliveryChunk) -> dict[str, Any]:
    return {
        'type': 'chunk.manifest',
        'requestId': request.request_id,
        'deliverySessionId': request.delivery_session_id,
        'chunkId': chunk.chunk_id,
        'manifest': chunk.manifest,
    }


def chunk_data_frame(request: ChunkRequest, chunk: DeliveryChunk, offset: int = 0) -> dict[str, Any]:
    data = chunk.encrypted_data[offset:]
    return {
        'type': 'chunk.data',
        'requestId': request.request_id,
        'deliverySessionId': request.delivery_session_id,
        'chunkId': chunk.chunk_id,
        'offset': offset,
        'dataBase64': base64.b64encode(data).decode('ascii'),
    }


def chunk_end_frame(request: ChunkRequest, chunk: DeliveryChunk) -> dict[str, Any]:
    return {
        'type': 'chunk.end',
        'requestId': request.request_id,
        'deliverySessionId': request.delivery_session_id,
        'chunkId': chunk.chunk_id,
        'bytes': len(chunk.encrypted_data),
    }


def delivery_ack_frame(ack: DeliveryAck, request_id: str) -> dict[str, Any]:
    return {
        'type': 'delivery.ack',
        'requestId': request_id,
        'deliverySessionId': ack.session_id,
        'chunkId': ack.chunk_id,
        'buyerId': ack.buyer_id,
        'transportId': ack.transport_id,
        'status': ack.status,
    }


def delivery_error_frame(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        'type': 'delivery.error',
        'requestId': request_id,
        'code': code,
        'message': message,
    }


def response_frames_for_request(
    request: ChunkRequest,
    chunk_provider: Callable[[str], DeliveryChunk],
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for chunk_id in request.chunk_ids:
        chunk = chunk_provider(chunk_id)
        offset = int(request.resume_offsets.get(chunk_id, 0) or 0)
        if offset < 0 or offset > len(chunk.encrypted_data):
            raise ValueError(f'invalid resume offset for chunk {chunk_id}')
        frames.append(chunk_manifest_frame(request, chunk))
        frames.append(chunk_data_frame(request, chunk, offset=offset))
        frames.append(chunk_end_frame(request, chunk))
    return frames


def chunks_from_response(frames: list[dict[str, Any]]) -> list[DeliveryChunk]:
    manifests: dict[str, dict[str, Any]] = {}
    data_parts: dict[str, bytearray] = {}
    ended: set[str] = set()
    for frame in frames:
        frame_type = frame.get('type')
        chunk_id = str(frame.get('chunkId') or '')
        if frame_type == 'delivery.error':
            raise ValueError(str(frame.get('message') or 'stream delivery failed'))
        if not chunk_id:
            continue
        if frame_type == 'chunk.manifest':
            manifest = frame.get('manifest')
            if not isinstance(manifest, dict):
                raise ValueError('chunk.manifest frame must include manifest')
            manifests[chunk_id] = manifest
        elif frame_type == 'chunk.data':
            encoded = str(frame.get('dataBase64') or '')
            data_parts.setdefault(chunk_id, bytearray()).extend(base64.b64decode(encoded.encode('ascii')))
        elif frame_type == 'chunk.end':
            ended.add(chunk_id)

    chunks: list[DeliveryChunk] = []
    for chunk_id in ended:
        if chunk_id not in manifests:
            raise ValueError(f'missing manifest for chunk {chunk_id}')
        chunks.append(
            DeliveryChunk(
                chunk_id=chunk_id,
                manifest=manifests[chunk_id],
                encrypted_data=bytes(data_parts.get(chunk_id, bytearray())),
            )
        )
    return sorted(chunks, key=lambda item: item.chunk_id)
