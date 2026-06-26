"""Transport abstraction for peaqOS Stream delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


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
) -> dict[str, Any]:
    capability: dict[str, Any] = {
        'transportId': transport_id,
        'version': version,
        'features': list(features),
    }
    if params:
        capability['params'] = params
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
        self._transports[transport.transport_id] = transport

    def get(self, transport_id: str) -> StreamDeliveryTransport:
        try:
            return self._transports[transport_id]
        except KeyError as exc:
            raise KeyError(f'delivery transport is not registered: {transport_id}') from exc

    def negotiate(
        self,
        seller_capabilities: list[dict[str, Any]],
        buyer_capabilities: list[dict[str, Any]],
        preferred_transports: list[str] | None = None,
    ) -> StreamDeliveryTransport:
        preferred = preferred_transports or []
        buyer_ids = {str(item.get('transportId') or '') for item in buyer_capabilities}
        seller_ids = [str(item.get('transportId') or '') for item in seller_capabilities]
        candidates = [item for item in preferred if item in seller_ids and (not buyer_ids or item in buyer_ids)]
        candidates.extend(item for item in seller_ids if item and item not in candidates and (not buyer_ids or item in buyer_ids))
        for transport_id in candidates:
            if transport_id in self._transports:
                return self._transports[transport_id]
        raise ValueError('no compatible registered delivery transport found')
