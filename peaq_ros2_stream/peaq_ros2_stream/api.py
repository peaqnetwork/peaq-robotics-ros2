"""HTTP client for peaqOS Stream APIs."""

from __future__ import annotations

from typing import Any

import requests


class StreamApiError(RuntimeError):
    def __init__(self, status_code: int, payload: Any) -> None:
        super().__init__(f'stream api returned {status_code}: {payload}')
        self.status_code = status_code
        self.payload = payload


class StreamApiClient:
    def __init__(self, base_url: str, api_key: str = '', timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {'content-type': 'application/json'}
        if self.api_key:
            headers['authorization'] = f'Bearer {self.api_key}'
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        response = self.session.request(
            method,
            f'{self.base_url}{path}',
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        try:
            body = response.json()
        except Exception:
            body = {'error': response.text}
        if response.status_code >= 400:
            raise StreamApiError(response.status_code, body)
        return body

    def create_policy(self, machine_id: str, policy_payload: dict[str, Any]) -> dict[str, Any]:
        return self._request('POST', f'/api/v1/machines/{machine_id}/stream/policies', policy_payload)['item']

    def update_policy(self, machine_id: str, policy_id: str, policy_payload: dict[str, Any]) -> dict[str, Any]:
        return self._request('PATCH', f'/api/v1/machines/{machine_id}/stream/policies/{policy_id}', policy_payload)['item']

    def list_policies(self, machine_id: str) -> list[dict[str, Any]]:
        return self._request('GET', f'/api/v1/machines/{machine_id}/stream/policies')['items']

    def register_signing_key(
        self,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        key_id: str,
        public_key_hex: str,
    ) -> dict[str, Any]:
        return self._request(
            'POST',
            f'/api/v1/machines/{machine_id}/stream/signing-keys',
            {
                'agentId': agent_id,
                'agentToken': agent_token,
                'keyId': key_id,
                'publicKeyHex': public_key_hex,
            },
        )['item']

    def heartbeat(self, machine_id: str, agent_id: str, agent_token: str, policy_id: str = '') -> dict[str, Any]:
        payload = {'machineId': machine_id, 'agentId': agent_id, 'agentToken': agent_token}
        if policy_id:
            payload['policyId'] = policy_id
        return self._request('POST', '/api/v1/stream/heartbeat', payload)['item']

    def post_event(self, agent_token: str, envelope: dict[str, Any]) -> dict[str, Any]:
        return self._request('POST', '/api/v1/stream/events', {'agentToken': agent_token, 'envelope': envelope})['item']

    def post_batch(self, agent_token: str, envelopes: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request('POST', '/api/v1/stream/events/batch', {'agentToken': agent_token, 'items': envelopes})

    def patch_chain_receipt(
        self,
        receipt_id: str,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        tx_hash: str,
        data_hash: str,
    ) -> dict[str, Any]:
        return self._request(
            'PATCH',
            f'/api/v1/stream/events/{receipt_id}/chain-receipt',
            {
                'machineId': machine_id,
                'agentId': agent_id,
                'agentToken': agent_token,
                'txHash': tx_hash,
                'dataHash': data_hash,
            },
        )['item']

    def post_chunk(self, machine_id: str, agent_id: str, agent_token: str, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            'POST',
            '/api/v1/stream/chunks',
            {
                'machineId': machine_id,
                'agentId': agent_id,
                'agentToken': agent_token,
                'manifest': manifest,
            },
        )['item']

    def create_buyer_access(
        self,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        access: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            'POST',
            '/api/v1/stream/buyer-access',
            {
                'machineId': machine_id,
                'agentId': agent_id,
                'agentToken': agent_token,
                'access': access,
            },
        )['item']

    def list_buyer_access(self, chunk_id: str, buyer_id: str = '') -> list[dict[str, Any]]:
        suffix = f'?buyerId={buyer_id}' if buyer_id else ''
        return self._request('GET', f'/api/v1/stream/chunks/{chunk_id}/buyer-access{suffix}')['items']
