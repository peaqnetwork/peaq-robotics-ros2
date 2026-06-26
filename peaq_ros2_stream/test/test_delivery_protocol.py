from __future__ import annotations

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
