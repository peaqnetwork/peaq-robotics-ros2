from __future__ import annotations

import pytest

from peaq_ros2_stream.chunk_keys import StreamChunkKeyStore


def test_chunk_key_store_put_get_and_delete(tmp_path):
    store = StreamChunkKeyStore(str(tmp_path / 'keys.sqlite3'))

    store.put('chunk-1', 'aa' * 32)

    assert store.get('chunk-1') == 'aa' * 32

    store.put('chunk-1', 'bb' * 32)
    assert store.get('chunk-1') == 'bb' * 32

    store.delete('chunk-1')
    assert store.get('chunk-1') == ''


def test_chunk_key_store_rejects_invalid_key(tmp_path):
    store = StreamChunkKeyStore(str(tmp_path / 'keys.sqlite3'))

    with pytest.raises(ValueError, match='32-byte'):
        store.put('chunk-1', 'aa')
