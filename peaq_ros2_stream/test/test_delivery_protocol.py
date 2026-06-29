from __future__ import annotations

import asyncio

import pytest

from peaq_ros2_stream.delivery_protocol import (
    CHUNK_PROTOCOL_ID,
    ChunkRequest,
    chunk_request_frame,
    chunks_from_response,
    decode_frame_sequence,
    decode_frames,
    encode_frame_sequence,
    response_frames_for_request,
)
from peaq_ros2_stream.delivery_transport import DeliveryChunk
from peaq_ros2_stream.libp2p_delivery import (
    Libp2pChunkResponder,
    Libp2pDeliveryTransport,
    Libp2pPeer,
    PyLibp2pStreamRuntime,
    libp2p_peer_from_connection,
    new_libp2p_host,
    register_libp2p_chunk_handler,
)


class _Runtime:
    def __init__(self, responder: Libp2pChunkResponder) -> None:
        self.responder = responder
        self.calls = []

    async def request_response(self, peer_id, protocol_id, payload, params=None):
        self.calls.append(
            {
                'peer_id': peer_id,
                'protocol_id': protocol_id,
                'payload': payload,
                'params': params or {},
            }
        )
        return self.responder.respond(payload)


def _chunk(chunk_id='chunk-1') -> DeliveryChunk:
    return DeliveryChunk(
        chunk_id=chunk_id,
        manifest={
            'chunkId': chunk_id,
            'encryptedDataHash': f'sha256:{chunk_id}',
        },
        encrypted_data=f'encrypted-{chunk_id}'.encode('utf8'),
    )


def test_chunk_protocol_encodes_length_prefixed_request_and_response_frames():
    request = ChunkRequest(
        purchase_id='purchase-1',
        delivery_session_id='delivery-1',
        buyer_id='did:peaq:buyer',
        chunk_ids=['chunk-1'],
        request_id='req-1',
    )
    payload = encode_frame_sequence([chunk_request_frame(request)])

    partial_frames, remainder = decode_frames(payload[:8])
    assert partial_frames == []
    assert remainder == payload[:8]

    frames = decode_frame_sequence(payload)
    assert frames[0]['type'] == 'chunk.request'
    assert frames[0]['protocol'] == CHUNK_PROTOCOL_ID
    assert frames[0]['deliverySessionId'] == 'delivery-1'

    response = response_frames_for_request(
        request,
        lambda chunk_id: _chunk(chunk_id),
    )
    delivered = chunks_from_response(response)

    assert [frame['type'] for frame in response] == [
        'chunk.manifest',
        'chunk.data',
        'chunk.end',
    ]
    assert delivered == [_chunk('chunk-1')]


def test_libp2p_delivery_transport_uses_chunk_protocol_and_runtime_boundary():
    responder = Libp2pChunkResponder(lambda chunk_id: _chunk(chunk_id))
    runtime = _Runtime(responder)
    transport = Libp2pDeliveryTransport(runtime)
    request = ChunkRequest(
        purchase_id='purchase-1',
        delivery_session_id='delivery-1',
        buyer_id='did:peaq:buyer',
        chunk_ids=['chunk-1'],
        request_id='req-1',
    )

    delivered = asyncio.run(
        transport.fetch_chunks(
            Libp2pPeer(
                peer_id='12D3KooWSeller',
                multiaddrs=['/ip4/127.0.0.1/tcp/4001'],
            ),
            request,
        )
    )

    assert delivered == [_chunk('chunk-1')]
    assert runtime.calls[0]['peer_id'] == '12D3KooWSeller'
    assert runtime.calls[0]['protocol_id'] == CHUNK_PROTOCOL_ID
    assert runtime.calls[0]['params']['connection']['addresses'] == [
        '/ip4/127.0.0.1/tcp/4001',
    ]
    capability = transport.capability({'nodeId': '12D3KooWSeller'})
    assert capability['transportId'] == 'peaqos-p2p'
    assert capability['connection'] == {'type': 'p2p', 'nodeId': '12D3KooWSeller'}
    assert capability['protocols'] == [CHUNK_PROTOCOL_ID]


def test_public_connection_maps_to_libp2p_peer_boundary():
    peer = libp2p_peer_from_connection(
        {
            'type': 'p2p',
            'nodeId': '12D3KooWSeller',
            'addresses': ['/ip4/127.0.0.1/tcp/4001'],
        }
    )

    assert peer.peer_id == '12D3KooWSeller'
    assert peer.multiaddrs == ['/ip4/127.0.0.1/tcp/4001']


def test_py_libp2p_runtime_moves_chunks_between_two_hosts():
    pytest.importorskip('libp2p')
    trio = pytest.importorskip('trio')
    multiaddr = pytest.importorskip('multiaddr')

    async def _scenario():
        seller = new_libp2p_host(['/ip4/127.0.0.1/tcp/0'])
        buyer = new_libp2p_host(['/ip4/127.0.0.1/tcp/0'])
        chunks = {
            'chunk-1': _chunk('chunk-1'),
            'chunk-2': _chunk('chunk-2'),
        }
        register_libp2p_chunk_handler(
            seller,
            Libp2pChunkResponder(lambda chunk_id: chunks[chunk_id]),
        )

        seller_listen = multiaddr.Multiaddr('/ip4/127.0.0.1/tcp/0')
        buyer_listen = multiaddr.Multiaddr('/ip4/127.0.0.1/tcp/0')
        async with seller.run([seller_listen]), buyer.run([buyer_listen]):
            runtime = PyLibp2pStreamRuntime(buyer, timeout_seconds=10)
            transport = Libp2pDeliveryTransport(runtime)
            request = ChunkRequest(
                purchase_id='purchase-1',
                delivery_session_id='delivery-1',
                buyer_id='did:peaq:buyer',
                chunk_ids=['chunk-1', 'chunk-2'],
                request_id='req-1',
            )
            peer = Libp2pPeer(
                peer_id=str(seller.get_id()),
                multiaddrs=[str(addr) for addr in seller.get_addrs()],
            )

            delivered = await transport.fetch_chunks(peer, request)

            assert delivered == [chunks['chunk-1'], chunks['chunk-2']]

    trio.run(_scenario)
