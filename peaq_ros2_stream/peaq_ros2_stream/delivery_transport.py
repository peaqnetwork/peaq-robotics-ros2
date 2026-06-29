"""Transport abstraction for peaqOS Stream delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


PEAQOS_P2P_TRANSPORT_ID = 'peaqos-p2p'


def normalize_transport_id(transport_id: str) -> str:
    return PEAQOS_P2P_TRANSPORT_ID if transport_id == 'libp2p' else transport_id


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def delivery_connection(params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not params:
        return None
    source = params.get('connection') if isinstance(params.get('connection'), dict) else params
    node_id = str(
        source.get('nodeId')
        or source.get('peerId')
        or source.get('endpointId')
        or ''
    ).strip()
    addresses = _string_list(source.get('addresses') or source.get('multiaddrs'))
    hints = source.get('hints') if isinstance(source.get('hints'), dict) else {}
    extra_hints = {
        key: value
        for key, value in source.items()
        if key not in {'type', 'nodeId', 'peerId', 'endpointId', 'addresses', 'multiaddrs', 'hints'}
    }
    connection: dict[str, Any] = {
        'type': str(source.get('type') or 'p2p'),
    }
    if node_id:
        connection['nodeId'] = node_id
    if addresses:
        connection['addresses'] = addresses
    if hints or extra_hints:
        connection['hints'] = {**hints, **extra_hints}
    return connection


@dataclass(frozen=True)
class DeliveryChunk:
    chunk_id: str
    manifest: dict[str, Any]
    encrypted_data: bytes


@dataclass(frozen=True)
class DeliveryAck:
    session_id: str
    chunk_id: str
    buyer_id: str
    transport_id: str
    status: str = 'received'


class StreamDeliveryTransport(Protocol):
    transport_id: str
    version: str
    features: tuple[str, ...]

    def capability(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def publish_chunk(self, session_id: str, chunk: DeliveryChunk) -> None:
        ...

    def fetch_chunk(self, session_id: str, chunk_id: str) -> DeliveryChunk:
        ...

    def acknowledge_chunk(self, session_id: str, chunk_id: str, buyer_id: str) -> DeliveryAck:
        ...


def transport_capability(
    transport_id: str,
    version: str,
    features: tuple[str, ...] | list[str],
    params: dict[str, Any] | None = None,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capability: dict[str, Any] = {
        'transportId': normalize_transport_id(transport_id),
        'version': version,
        'features': list(features),
    }
    public_connection = connection or delivery_connection(params)
    if public_connection:
        capability['connection'] = public_connection
    return capability


class LocalMemoryDeliveryTransport:
    def __init__(
        self,
        transport_id: str = 'local-memory',
        version: str = 'v1',
        features: tuple[str, ...] = ('chunks',),
    ) -> None:
        self.transport_id = transport_id
        self.version = version
        self.features = features
        self._sessions: dict[str, dict[str, DeliveryChunk]] = {}
        self._acks: list[DeliveryAck] = []

    def capability(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return transport_capability(self.transport_id, self.version, self.features, params)

    def publish_chunk(self, session_id: str, chunk: DeliveryChunk) -> None:
        if not session_id:
            raise ValueError('session_id is required')
        if not chunk.chunk_id:
            raise ValueError('chunk.chunk_id is required')
        self._sessions.setdefault(session_id, {})[chunk.chunk_id] = chunk

    def fetch_chunk(self, session_id: str, chunk_id: str) -> DeliveryChunk:
        try:
            return self._sessions[session_id][chunk_id]
        except KeyError as exc:
            raise KeyError(f'chunk {chunk_id} is not available for delivery session {session_id}') from exc

    def acknowledge_chunk(self, session_id: str, chunk_id: str, buyer_id: str) -> DeliveryAck:
        self.fetch_chunk(session_id, chunk_id)
        ack = DeliveryAck(session_id=session_id, chunk_id=chunk_id, buyer_id=buyer_id, transport_id=self.transport_id)
        self._acks.append(ack)
        return ack

    def list_acks(self) -> list[DeliveryAck]:
        return list(self._acks)


class StreamDeliveryTransportRegistry:
    def __init__(self) -> None:
        self._transports: dict[str, StreamDeliveryTransport] = {}

    def register(self, transport: StreamDeliveryTransport) -> None:
        self._transports[normalize_transport_id(transport.transport_id)] = transport

    def get(self, transport_id: str) -> StreamDeliveryTransport:
        try:
            return self._transports[normalize_transport_id(transport_id)]
        except KeyError as exc:
            raise KeyError(f'delivery transport is not registered: {transport_id}') from exc

    def negotiate(
        self,
        seller_capabilities: list[dict[str, Any]],
        buyer_capabilities: list[dict[str, Any]],
        preferred_transports: list[str] | None = None,
    ) -> StreamDeliveryTransport:
        preferred = [normalize_transport_id(item) for item in preferred_transports or []]
        buyer_ids = {normalize_transport_id(str(item.get('transportId') or '')) for item in buyer_capabilities}
        seller_ids = [normalize_transport_id(str(item.get('transportId') or '')) for item in seller_capabilities]
        candidates = [item for item in preferred if item in seller_ids and (not buyer_ids or item in buyer_ids)]
        candidates.extend(item for item in seller_ids if item and item not in candidates and (not buyer_ids or item in buyer_ids))
        for transport_id in candidates:
            if transport_id in self._transports:
                return self._transports[transport_id]
        raise ValueError('no compatible registered delivery transport found')
