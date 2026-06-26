from __future__ import annotations

import pytest

from peaq_ros2_stream.delivery_transport import (
    DeliveryChunk,
    LocalMemoryDeliveryTransport,
    StreamDeliveryTransportRegistry,
    transport_capability,
)


def test_local_memory_transport_moves_encrypted_chunks_and_records_ack():
    transport = LocalMemoryDeliveryTransport(transport_id='libp2p', features=('chunks', 'resume'))
    chunk = DeliveryChunk(
        chunk_id='chunk-1',
        manifest={
            'chunkId': 'chunk-1',
            'encryptedDataHash': 'sha256:test',
        },
        encrypted_data=b'encrypted-bytes',
    )

    capability = transport.capability({'peerId': 'seller-peer'})
    transport.publish_chunk('session-1', chunk)
    delivered = transport.fetch_chunk('session-1', 'chunk-1')
    ack = transport.acknowledge_chunk('session-1', 'chunk-1', 'did:peaq:buyer')

    assert capability == {
        'transportId': 'libp2p',
        'version': 'v1',
        'features': ['chunks', 'resume'],
        'params': {'peerId': 'seller-peer'},
    }
    assert delivered == chunk
    assert ack.transport_id == 'libp2p'
    assert ack.status == 'received'
    assert transport.list_acks() == [ack]


def test_transport_registry_negotiates_preferred_registered_transport():
    registry = StreamDeliveryTransportRegistry()
    local = LocalMemoryDeliveryTransport(transport_id='local-memory')
    p2p = LocalMemoryDeliveryTransport(transport_id='libp2p')
    registry.register(local)
    registry.register(p2p)

    selected = registry.negotiate(
        seller_capabilities=[
            transport_capability('local-memory', 'v1', ['chunks']),
            transport_capability('libp2p', 'v1', ['chunks', 'resume']),
        ],
        buyer_capabilities=[
            transport_capability('libp2p', 'v1', ['chunks']),
        ],
        preferred_transports=['libp2p', 'local-memory'],
    )

    assert selected is p2p


def test_transport_registry_fails_when_no_common_registered_transport():
    registry = StreamDeliveryTransportRegistry()
    registry.register(LocalMemoryDeliveryTransport(transport_id='local-memory'))

    with pytest.raises(ValueError, match='no compatible registered delivery transport'):
        registry.negotiate(
            seller_capabilities=[transport_capability('libp2p', 'v1', ['chunks'])],
            buyer_capabilities=[transport_capability('libp2p', 'v1', ['chunks'])],
        )
