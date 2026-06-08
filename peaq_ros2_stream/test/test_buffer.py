from __future__ import annotations

import pytest

from peaq_ros2_stream.buffer import StreamEventBuffer, flush_due


def _event(sequence: int) -> dict:
    return {
        'machineId': 'mach_1',
        'topic': '/battery',
        'policyVersion': 1,
        'sequenceNumber': sequence,
        'payloadHash': f'sha256:{sequence:064x}',
    }


def test_buffer_retries_failed_sends_and_marks_success(tmp_path):
    buffer = StreamEventBuffer(str(tmp_path / 'events.sqlite3'), retry_interval_seconds=10)
    event_id = buffer.enqueue(_event(1), now=100.0)

    sent, failed = flush_due(buffer, lambda envelope: (_ for _ in ()).throw(RuntimeError('offline')), now=100.0)
    assert sent == 0
    assert failed == 1
    assert buffer.due(now=101.0) == []

    sent, failed = flush_due(buffer, lambda envelope: envelope, now=110.0)
    assert sent == 1
    assert failed == 0
    assert event_id not in buffer.all_ids()


def test_buffer_drops_oldest_on_overflow(tmp_path):
    buffer = StreamEventBuffer(str(tmp_path / 'events.sqlite3'), max_events=2, overflow='drop_oldest')
    first = buffer.enqueue(_event(1), now=1.0)
    second = buffer.enqueue(_event(2), now=2.0)
    third = buffer.enqueue(_event(3), now=3.0)

    ids = buffer.all_ids()
    assert first not in ids
    assert second in ids
    assert third in ids


def test_buffer_prunes_expired_events(tmp_path):
    buffer = StreamEventBuffer(str(tmp_path / 'events.sqlite3'), retention_seconds=5)
    old = buffer.enqueue(_event(1), now=10.0)
    recent = buffer.enqueue(_event(2), now=14.0)

    buffer.prune(now=16.0)

    ids = buffer.all_ids()
    assert old not in ids
    assert recent in ids


def test_buffer_can_pause_on_overflow(tmp_path):
    buffer = StreamEventBuffer(str(tmp_path / 'events.sqlite3'), max_events=1, overflow='pause')
    buffer.enqueue(_event(1), now=1.0)
    with pytest.raises(OverflowError):
        buffer.enqueue(_event(2), now=2.0)
