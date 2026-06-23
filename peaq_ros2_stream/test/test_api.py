from __future__ import annotations

from peaq_ros2_stream.api import StreamApiClient


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, json, headers, timeout):
        self.calls.append({'method': method, 'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        if url == 'https://api.example/api/v1/stream/listings':
            return _Response({'items': [{'id': 'listing-1'}]})
        if url == 'https://api.example/api/v1/payment-rails':
            return _Response({'items': [{'type': 'x402'}, {'type': 'transfer'}]})
        if url == 'https://api.example/api/v1/delivery-transports':
            return _Response({'items': [{'mode': 'p2p', 'transportId': 'libp2p'}]})
        if url.endswith('/stream/orders/order-1/prepare-access'):
            return _Response({'item': {'id': 'order-1'}, 'access': [], 'deliverySession': {'id': 'delivery-1'}})
        return _Response({'item': {'id': 'created'}})


def test_stream_api_client_uses_listing_order_and_access_paths():
    session = _Session()
    client = StreamApiClient('https://api.example', api_key='api-key', timeout=3)
    client.session = session

    listing = client.create_listing(
        'machine-1',
        {
            'title': 'Weather chunks',
            'chunkIds': ['chunk-1'],
            'price': {'amount': 1, 'currency': 'PEAQ'},
        },
    )
    order = client.create_order('listing-1', 'did:peaq:buyer', '11' * 32)
    payment = client.record_order_payment('order-1', 'payment-ref')
    prepared = client.prepare_order_access(
        'order-1',
        'machine-1',
        'agent-1',
        'token',
        [
            {
                'schemaVersion': 'peaq.stream.buyer-access.v1',
                'chunkId': 'chunk-1',
                'buyer': {
                    'recipientId': 'did:peaq:buyer',
                    'recipientType': 'buyer',
                    'algorithm': 'x25519-sealedbox',
                    'publicKeyHex': '11' * 32,
                    'wrappedKeyHex': '22' * 48,
                },
            }
        ],
        delivery={'mode': 'walrus'},
    )

    assert listing == {'id': 'created'}
    assert order == {'id': 'created'}
    assert payment == {'id': 'created'}
    assert prepared['deliverySession']['id'] == 'delivery-1'
    assert session.calls[0]['method'] == 'POST'
    assert session.calls[0]['url'] == 'https://api.example/api/v1/machines/machine-1/stream/listings'
    assert session.calls[1]['url'] == 'https://api.example/api/v1/stream/orders'
    assert session.calls[2]['url'] == 'https://api.example/api/v1/stream/orders/order-1/payment'
    assert session.calls[3]['url'] == 'https://api.example/api/v1/stream/orders/order-1/prepare-access'
    assert session.calls[3]['json']['delivery'] == {'mode': 'walrus'}


def test_stream_api_client_enrolls_stream_agent_and_reads_machine():
    session = _Session()
    client = StreamApiClient('https://api.example')
    client.session = session

    machine = client.get_machine('machine-1')
    agent = client.enroll_machine_agent('machine-1', label='Seller stream')

    assert machine == {'id': 'created'}
    assert agent == {'id': 'created'}
    assert session.calls[0]['method'] == 'GET'
    assert session.calls[0]['url'] == 'https://api.example/api/v1/machines/machine-1'
    assert session.calls[1]['method'] == 'POST'
    assert session.calls[1]['url'] == 'https://api.example/api/v1/machines/machine-1/agents/enrollment'
    assert session.calls[1]['json'] == {
        'label': 'Seller stream',
        'allowedProviderKeys': ['stream'],
    }


def test_stream_api_client_uses_purchase_start_paths():
    session = _Session()
    client = StreamApiClient('https://api.example')
    client.session = session

    rails = client.list_payment_rails()
    transports = client.list_delivery_transports()
    capability = client.put_delivery_capabilities(
        'machine-1',
        'agent-1',
        [
            {
                'transportId': 'libp2p',
                'version': 'v1',
                'features': ['chunks'],
            }
        ],
        resource_types=['stream.bundle'],
        expires_at='2027-01-01T00:00:00Z',
    )
    purchase = client.create_purchase(
        resource={
            'type': 'stream.listing',
            'listingId': 'listing-1',
            'selection': {'chunkIds': ['chunk-1']},
        },
        buyer={
            'id': 'did:peaq:buyer',
            'publicKey': {'type': 'x25519', 'publicKeyHex': '11' * 32},
            'deliveryCapabilities': [
                {
                    'transportId': 'libp2p',
                    'version': 'v1',
                    'features': ['chunks'],
                }
            ],
        },
        delivery={'acceptableModes': ['p2p'], 'preferredTransports': ['libp2p']},
    )
    intent = client.create_purchase_payment_intent(
        'purchase-1',
        {
            'type': 'transfer',
            'destination': {
                'chain': 'peaq',
                'token': 'PEAQ',
                'payTo': '0x1111111111111111111111111111111111111111',
            },
        },
    )

    assert rails == [{'type': 'x402'}, {'type': 'transfer'}]
    assert transports == [{'mode': 'p2p', 'transportId': 'libp2p'}]
    assert capability == {'id': 'created'}
    assert purchase == {'id': 'created'}
    assert intent == {'id': 'created'}
    assert session.calls[0]['url'] == 'https://api.example/api/v1/payment-rails'
    assert session.calls[1]['url'] == 'https://api.example/api/v1/delivery-transports'
    assert session.calls[2]['method'] == 'PUT'
    assert session.calls[2]['url'] == 'https://api.example/api/v1/machines/machine-1/delivery-capabilities'
    assert session.calls[2]['json']['resourceTypes'] == ['stream.bundle']
    assert session.calls[3]['url'] == 'https://api.example/api/v1/purchases'
    assert session.calls[3]['json']['delivery']['preferredTransports'] == ['libp2p']
    assert session.calls[4]['url'] == 'https://api.example/api/v1/purchases/purchase-1/payment-intent'
