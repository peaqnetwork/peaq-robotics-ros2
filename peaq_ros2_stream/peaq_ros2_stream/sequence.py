"""Persistent sequence numbers scoped by machine, topic, and policy version."""

from __future__ import annotations

import json
import os
from typing import Any


class SequenceStore:
    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)

    def _load(self) -> dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, 'r', encoding='utf8') as handle:
            return json.load(handle)

    def _save(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        with open(self.path, 'w', encoding='utf8') as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def next(self, machine_id: str, topic: str, policy_version: int) -> int:
        key = f'{machine_id}:{topic}:{int(policy_version)}'
        data = self._load()
        current = int(data.get(key, -1))
        value = current + 1
        data[key] = value
        self._save(data)
        return value
