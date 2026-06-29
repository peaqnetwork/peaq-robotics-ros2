from __future__ import annotations

import pytest

from peaq_ros2_stream.delivery_transport import (
    DeliveryChunk,
    LocalMemoryDeliveryTransport,
    PEAQOS_P2P_TRANSPORT_ID,
    StreamDeliveryTransportRegistry,
    delivery_connect,
    transport_capability,
)


def test_local_memory_transport_moves_encrypted_chunks_and_records_ack():
    transport = LocalMemoryDeliveryTransport(transport_id=PEAQOS_P2P_TRANSPORT_ID, features=('chunks', 'resume'))
    chunk = DeliveryChunk(
        chunk_id='chunk-1',
        manifest={
            'chunkId': 'chunk-1',
            'encryptedDataHash': 'sha256:test',
        },
        encrypted_data=b'encrypted-bytes',
    )

    capability = transport.capability({'nodeId': 'seller-peer'})
    transport.publish_chunk('session-1', chunk)
    delivered = transport.fetch_chunk('session-1', 'chunk-1')
    ack = transport.acknowledge_chunk('session-1', 'chunk-1', 'did:peaq:buyer')

    assert capability == {
        'transportId': PEAQOS_P2P_TRANSPORT_ID,
        'version': 'v1',
        'features': ['chunks', 'resume'],
    }
    assert delivered == chunk
    assert ack.transport_id == PEAQOS_P2P_TRANSPORT_ID
    assert ack.status == 'received'
    assert transport.list_acks() == [ack]


def test_transport_registry_negotiates_preferred_registered_transport():
    registry = StreamDeliveryTransportRegistry()
    local = LocalMemoryDeliveryTransport(transport_id='local-memory')
    p2p = LocalMemoryDeliveryTransport(transport_id=PEAQOS_P2P_TRANSPORT_ID)
    registry.register(local)
    registry.register(p2p)

    selected = registry.negotiate(
        seller_capabilities=[
            transport_capability('local-memory', 'v1', ['chunks']),
            transport_capability(PEAQOS_P2P_TRANSPORT_ID, 'v1', ['chunks', 'resume']),
        ],
        buyer_capabilities=[
            transport_capability(PEAQOS_P2P_TRANSPORT_ID, 'v1', ['chunks']),
        ],
        preferred_transports=[PEAQOS_P2P_TRANSPORT_ID, 'local-memory'],
    )

    assert selected is p2p


def test_transport_registry_fails_when_no_common_registered_transport():
    registry = StreamDeliveryTransportRegistry()
    registry.register(LocalMemoryDeliveryTransport(transport_id='local-memory'))

    with pytest.raises(ValueError, match='no compatible registered delivery transport'):
        registry.negotiate(
            seller_capabilities=[transport_capability(PEAQOS_P2P_TRANSPORT_ID, 'v1', ['chunks'])],
            buyer_capabilities=[transport_capability(PEAQOS_P2P_TRANSPORT_ID, 'v1', ['chunks'])],
        )


def test_delivery_connect_requires_short_lived_url_shape():
    connect = delivery_connect(
        {
            'type': 'peaqos-p2p-url',
            'url': 'peaqos-p2p://seller-peer?addr=%2Fip4%2F127.0.0.1%2Ftcp%2F4001',
            'expiresAt': '2027-01-01T00:00:00.000Z',
        }
    )

    assert connect == {
        'type': 'peaqos-p2p-url',
        'url': 'peaqos-p2p://seller-peer?addr=%2Fip4%2F127.0.0.1%2Ftcp%2F4001',
        'expiresAt': '2027-01-01T00:00:00.000Z',
    }
