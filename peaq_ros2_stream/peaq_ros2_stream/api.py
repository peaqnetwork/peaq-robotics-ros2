"""HTTP client for peaqOS Stream APIs."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

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

    def get_machine(self, machine_id: str) -> dict[str, Any]:
        return self._request('GET', f'/api/v1/machines/{machine_id}')['item']

    def enroll_machine_agent(
        self,
        machine_id: str,
        label: str = 'Stream runtime',
        allowed_provider_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            'POST',
            f'/api/v1/machines/{machine_id}/agents/enrollment',
            {
                'label': label,
                'allowedProviderKeys': allowed_provider_keys or ['stream'],
            },
        )['item']

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

    def post_chunk(
        self,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        manifest: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'machineId': machine_id,
            'agentId': agent_id,
            'agentToken': agent_token,
            'manifest': manifest,
        }
        if metadata:
            payload['metadata'] = metadata
        return self._request(
            'POST',
            '/api/v1/stream/chunks',
            payload,
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
        suffix = f'?{urlencode({"buyerId": buyer_id})}' if buyer_id else ''
        return self._request('GET', f'/api/v1/stream/chunks/{chunk_id}/buyer-access{suffix}')['items']

    def create_listing(self, machine_id: str, listing: dict[str, Any]) -> dict[str, Any]:
        return self._request('POST', f'/api/v1/machines/{machine_id}/stream/listings', listing)['item']

    def list_listings(self, machine_id: str = '', include_inactive: bool = False) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if machine_id:
            params['machineId'] = machine_id
        if include_inactive:
            params['includeInactive'] = 'true'
        suffix = f'?{urlencode(params)}' if params else ''
        return self._request('GET', f'/api/v1/stream/listings{suffix}')['items']

    def list_payment_rails(self) -> list[dict[str, Any]]:
        return self._request('GET', '/api/v1/payment-rails')['items']

    def list_delivery_transports(self) -> list[dict[str, Any]]:
        return self._request('GET', '/api/v1/delivery-transports')['items']

    def put_delivery_capabilities(
        self,
        machine_id: str,
        agent_id: str,
        capabilities: list[dict[str, Any]],
        resource_types: list[str] | None = None,
        expires_at: str = '',
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'agentId': agent_id,
            'capabilities': capabilities,
        }
        if resource_types:
            payload['resourceTypes'] = resource_types
        if expires_at:
            payload['expiresAt'] = expires_at
        return self._request('PUT', f'/api/v1/machines/{machine_id}/delivery-capabilities', payload)['item']

    def create_order(
        self,
        listing_id: str,
        buyer_id: str,
        buyer_public_key_hex: str,
        chunk_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'listingId': listing_id,
            'buyerId': buyer_id,
            'buyerPublicKeyHex': buyer_public_key_hex,
        }
        if chunk_ids:
            payload['chunkIds'] = chunk_ids
        return self._request('POST', '/api/v1/stream/orders', payload)['item']

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request('GET', f'/api/v1/stream/orders/{order_id}')['item']

    def get_order_delivery(self, order_id: str, buyer_id: str) -> dict[str, Any]:
        return self._request(
            'GET',
            f'/api/v1/stream/orders/{order_id}/delivery?{urlencode({"buyerId": buyer_id})}',
        )

    def create_purchase(
        self,
        resource: dict[str, Any],
        buyer: dict[str, Any],
        delivery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'resource': resource,
            'buyer': buyer,
        }
        if delivery:
            payload['delivery'] = delivery
        return self._request('POST', '/api/v1/purchases', payload)['item']

    def get_purchase(self, purchase_id: str) -> dict[str, Any]:
        return self._request('GET', f'/api/v1/purchases/{purchase_id}')['item']

    def create_purchase_payment_intent(
        self,
        purchase_id: str,
        rail: dict[str, Any],
        payer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {'rail': rail}
        if payer:
            payload['payer'] = payer
        return self._request('POST', f'/api/v1/purchases/{purchase_id}/payment-intent', payload)['item']

    def list_machine_orders(self, machine_id: str) -> list[dict[str, Any]]:
        return self._request('GET', f'/api/v1/machines/{machine_id}/stream/orders')['items']

    def record_order_payment(
        self,
        order_id: str,
        payment_reference: str,
        proof: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {'paymentReference': payment_reference}
        if proof:
            payload['proof'] = proof
        return self._request('POST', f'/api/v1/stream/orders/{order_id}/payment', payload)['item']

    def prepare_order_access(
        self,
        order_id: str,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        items: list[dict[str, Any]],
        delivery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'machineId': machine_id,
            'agentId': agent_id,
            'agentToken': agent_token,
            'items': items,
        }
        if delivery:
            payload['delivery'] = delivery
        return self._request('POST', f'/api/v1/stream/orders/{order_id}/prepare-access', payload)

    def poll_delivery_sessions(
        self,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self._request(
            'POST',
            '/api/v1/stream/delivery-sessions/poll',
            {
                'machineId': machine_id,
                'agentId': agent_id,
                'agentToken': agent_token,
                'statuses': statuses or ['requested'],
            },
        )['items']

    def update_delivery_session(
        self,
        session_id: str,
        machine_id: str,
        agent_id: str,
        agent_token: str,
        status: str,
        delivery_url: str = '',
        message: str = '',
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'machineId': machine_id,
            'agentId': agent_id,
            'agentToken': agent_token,
            'status': status,
        }
        if delivery_url:
            payload['deliveryUrl'] = delivery_url
        if message:
            payload['message'] = message
        return self._request('PATCH', f'/api/v1/stream/delivery-sessions/{session_id}', payload)['item']
