"""libp2p delivery adapter for peaqOS Stream."""

from __future__ import annotations

import struct
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .delivery_protocol import (
    CHUNK_PROTOCOL_ENCODING,
    CHUNK_PROTOCOL_ID,
    ChunkRequest,
    chunk_request_frame,
    chunks_from_response,
    decode_frames,
    decode_frame_sequence,
    delivery_error_frame,
    encode_frame,
    encode_frame_sequence,
    MAX_FRAME_BYTES,
    parse_chunk_request,
    response_frames_for_request,
)
from .delivery_transport import (
    PEAQOS_P2P_TRANSPORT_ID,
    PEAQOS_P2P_CONNECT_TYPE,
    DeliveryChunk,
    delivery_connection,
    delivery_connect,
    transport_capability,
)


class Libp2pRequestRuntime(Protocol):
    async def request_response(
        self,
        peer_id: str,
        protocol_id: str,
        payload: bytes,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        ...


class Libp2pRuntimeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Libp2pPeer:
    peer_id: str
    multiaddrs: list[str]


def libp2p_peer_from_connection(connection: dict[str, Any]) -> Libp2pPeer:
    normalized = delivery_connection(connection) or {}
    peer_id = str(normalized.get('nodeId') or '').strip()
    addresses = normalized.get('addresses')
    if not isinstance(addresses, list):
        addresses = []
    return Libp2pPeer(peer_id=peer_id, multiaddrs=[str(addr) for addr in addresses])


def libp2p_connect_url(
    peer: Libp2pPeer,
    *,
    session_id: str = '',
    expires_at: str = '',
) -> str:
    query: dict[str, list[str] | str] = {
        'addr': peer.multiaddrs,
    }
    if session_id:
        query['session'] = session_id
    if expires_at:
        query['expiresAt'] = expires_at
    return f'peaqos-p2p://{quote(peer.peer_id, safe="")}?{urlencode(query, doseq=True)}'


def libp2p_peer_from_connect(connect: dict[str, Any]) -> Libp2pPeer:
    handoff = delivery_connect(connect)
    if handoff is None:
        raise ValueError('p2p connect handoff is required')
    parsed = urlparse(handoff['url'])
    if parsed.scheme != 'peaqos-p2p':
        raise ValueError('p2p connect url must use peaqos-p2p scheme')
    peer_id = unquote(parsed.netloc or parsed.path.strip('/'))
    query = parse_qs(parsed.query)
    addresses = query.get('addr') or query.get('address') or []
    if not peer_id:
        raise ValueError('p2p connect url must include a peer id')
    if not addresses:
        raise ValueError('p2p connect url must include at least one addr query value')
    return Libp2pPeer(peer_id=peer_id, multiaddrs=[str(addr) for addr in addresses])


class Libp2pDeliveryTransport:
    def __init__(
        self,
        runtime: Libp2pRequestRuntime,
        version: str = 'v1',
        features: tuple[str, ...] = ('chunks', 'resume'),
    ) -> None:
        self.transport_id = PEAQOS_P2P_TRANSPORT_ID
        self.version = version
        self.features = features
        self.runtime = runtime

    def capability(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        capability = transport_capability(
            self.transport_id,
            self.version,
            self.features,
        )
        capability['protocols'] = [CHUNK_PROTOCOL_ID]
        capability['encoding'] = CHUNK_PROTOCOL_ENCODING
        return capability

    def connect_handoff(
        self,
        peer: Libp2pPeer,
        *,
        expires_at: str,
        session_id: str = '',
    ) -> dict[str, str]:
        return {
            'type': PEAQOS_P2P_CONNECT_TYPE,
            'url': libp2p_connect_url(peer, session_id=session_id, expires_at=expires_at),
            'expiresAt': expires_at,
        }

    async def fetch_chunks_from_connect(
        self,
        connect: dict[str, Any],
        request: ChunkRequest,
        params: dict[str, Any] | None = None,
    ) -> list[DeliveryChunk]:
        return await self.fetch_chunks(libp2p_peer_from_connect(connect), request, params=params)

    async def fetch_chunks(
        self,
        peer: Libp2pPeer,
        request: ChunkRequest,
        params: dict[str, Any] | None = None,
    ) -> list[DeliveryChunk]:
        payload = encode_frame_sequence([chunk_request_frame(request)])
        response = await self.runtime.request_response(
            peer.peer_id,
            CHUNK_PROTOCOL_ID,
            payload,
            {
                'connection': delivery_connection(
                    {'nodeId': peer.peer_id, 'addresses': peer.multiaddrs}
                ),
                **(params or {}),
            },
        )
        return chunks_from_response(decode_frame_sequence(response))


class Libp2pChunkResponder:
    def __init__(self, chunk_provider: Callable[[str], DeliveryChunk]) -> None:
        self.chunk_provider = chunk_provider

    def respond(self, payload: bytes) -> bytes:
        frames = decode_frame_sequence(payload)
        if not frames:
            raise ValueError('libp2p stream did not include a chunk request')
        request = parse_chunk_request(frames[0])
        response_frames = response_frames_for_request(request, self.chunk_provider)
        return encode_frame_sequence(response_frames)


class PyLibp2pStreamRuntime:
    def __init__(
        self,
        host: Any,
        timeout_seconds: float = 15,
        max_response_bytes: int = MAX_FRAME_BYTES * 16,
    ) -> None:
        self.host = host
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def request_response(
        self,
        peer_id: str,
        protocol_id: str,
        payload: bytes,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        libp2p_types = _load_libp2p_types()
        peer_info = _peer_info_from_params(peer_id, params or {}, libp2p_types)
        trio = libp2p_types['trio']
        protocol = libp2p_types['TProtocol'](protocol_id)
        expected_chunk_ids = _chunk_ids_from_request(payload)
        stream = None
        with trio.fail_after(self.timeout_seconds):
            await self.host.connect(peer_info)
            stream = await self.host.new_stream(peer_info.peer_id, [protocol])
            await stream.write(payload)
            response = await _read_stream_until_complete(
                stream,
                self.max_response_bytes,
                expected_chunk_ids,
            )
        if stream is not None:
            with suppress(Exception):
                await stream.close()
        return response


def new_libp2p_host(listen_addrs: list[str] | None = None, **kwargs: Any) -> Any:
    libp2p_types = _load_libp2p_types()
    libp2p = libp2p_types['libp2p']
    multiaddr_cls = libp2p_types['Multiaddr']
    parsed_addrs = (
        [multiaddr_cls(addr) for addr in listen_addrs]
        if listen_addrs
        else None
    )
    return libp2p.new_host(listen_addrs=parsed_addrs, **kwargs)


def register_libp2p_chunk_handler(
    host: Any,
    responder: Libp2pChunkResponder,
    protocol_id: str = CHUNK_PROTOCOL_ID,
) -> None:
    libp2p_types = _load_libp2p_types()
    protocol = libp2p_types['TProtocol'](protocol_id)

    async def _handler(stream: Any) -> None:
        try:
            request_payload = await _read_one_frame(stream)
            response_payload = responder.respond(request_payload)
        except Exception as exc:
            response_payload = encode_frame(
                delivery_error_frame('', 'delivery_failed', str(exc))
            )
        await stream.write(response_payload)
        await stream.close()

    host.set_stream_handler(protocol, _handler)


def _load_libp2p_types() -> dict[str, Any]:
    try:
        import libp2p
        import trio
        from libp2p.custom_types import TProtocol
        from libp2p.peer.id import ID
        from libp2p.peer.peerinfo import PeerInfo, info_from_p2p_addr
        from multiaddr import Multiaddr
    except ImportError as exc:
        raise Libp2pRuntimeUnavailable(
            'py-libp2p is required for real libp2p stream delivery'
        ) from exc
    return {
        'ID': ID,
        'Multiaddr': Multiaddr,
        'PeerInfo': PeerInfo,
        'TProtocol': TProtocol,
        'info_from_p2p_addr': info_from_p2p_addr,
        'libp2p': libp2p,
        'trio': trio,
    }


def _peer_info_from_params(
    peer_id: str,
    params: dict[str, Any],
    libp2p_types: dict[str, Any],
) -> Any:
    connection = delivery_connection(params.get('connection') if isinstance(params.get('connection'), dict) else params) or {}
    multiaddrs = connection.get('addresses') or params.get('multiaddrs')
    if not isinstance(multiaddrs, list) or not multiaddrs:
        raise ValueError('p2p peer addresses are required')

    resolved_peer_id = str(peer_id or connection.get('nodeId') or '')
    transport_addrs = []
    multiaddr_cls = libp2p_types['Multiaddr']
    peer_info_cls = libp2p_types['PeerInfo']
    peer_id_cls = libp2p_types['ID']
    info_from_p2p_addr = libp2p_types['info_from_p2p_addr']

    for raw_addr in multiaddrs:
        addr = multiaddr_cls(str(raw_addr))
        try:
            parsed_info = info_from_p2p_addr(addr)
        except ValueError:
            transport_addrs.append(addr)
            continue
        parsed_peer_id = str(parsed_info.peer_id)
        if resolved_peer_id and parsed_peer_id != resolved_peer_id:
            raise ValueError('p2p peer id does not match the provided address')
        resolved_peer_id = parsed_peer_id
        transport_addrs.extend(parsed_info.addrs)

    if not resolved_peer_id:
        raise ValueError('p2p peer id is required')
    return peer_info_cls(peer_id_cls.from_string(resolved_peer_id), transport_addrs)


async def _read_one_frame(stream: Any) -> bytes:
    header = await _read_exact(stream, 4)
    length = struct.unpack('>I', header)[0]
    if length > MAX_FRAME_BYTES:
        raise ValueError('stream delivery frame is too large')
    return header + await _read_exact(stream, length)


async def _read_exact(stream: Any, byte_count: int) -> bytes:
    data = bytearray()
    while len(data) < byte_count:
        try:
            chunk = await stream.read(byte_count - len(data))
        except Exception as exc:
            if _is_stream_eof(exc):
                break
            raise
        if not chunk:
            break
        data.extend(chunk)
    if len(data) != byte_count:
        raise ValueError('libp2p stream ended before the frame was complete')
    return bytes(data)


async def _read_stream_until_complete(
    stream: Any,
    max_response_bytes: int,
    expected_chunk_ids: set[str],
) -> bytes:
    data = bytearray()
    while True:
        try:
            chunk = await stream.read(64 * 1024)
        except Exception as exc:
            if _is_stream_eof(exc):
                break
            raise
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_response_bytes:
            raise ValueError('libp2p response exceeded the configured size limit')
        frames, remainder = decode_frames(bytes(data))
        if (
            not remainder
            and frames
            and _response_is_complete(frames, expected_chunk_ids)
        ):
            break
    return bytes(data)


def _response_is_complete(
    frames: list[dict[str, Any]],
    expected_chunk_ids: set[str],
) -> bool:
    if any(frame.get('type') == 'delivery.error' for frame in frames):
        return True
    manifests = {
        str(frame.get('chunkId') or '')
        for frame in frames
        if frame.get('type') == 'chunk.manifest'
    }
    ended = {
        str(frame.get('chunkId') or '')
        for frame in frames
        if frame.get('type') == 'chunk.end'
    }
    if expected_chunk_ids:
        return expected_chunk_ids.issubset(ended) and expected_chunk_ids.issubset(
            manifests
        )
    return bool(ended) and ended.issubset(manifests)


def _chunk_ids_from_request(payload: bytes) -> set[str]:
    try:
        frames = decode_frame_sequence(payload)
        request = parse_chunk_request(frames[0])
    except Exception:
        return set()
    return set(request.chunk_ids)


def _is_stream_eof(exc: Exception) -> bool:
    return exc.__class__.__name__ in {
        'MuxedStreamEOF',
        'MplexStreamEOF',
        'StreamEOF',
    }
