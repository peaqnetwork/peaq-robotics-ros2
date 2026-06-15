from __future__ import annotations

import sys

from peaq_ros2_stream.config import load_stream_agent_config_from_dict
from peaq_ros2_stream.encryption import encrypt_chunk_payload
from peaq_ros2_stream.storage_adapters import (
    GoogleDriveChunkStorageAdapter,
    LocalChunkStorageAdapter,
    S3ChunkStorageAdapter,
    WalrusChunkStorageAdapter,
    read_google_drive_file,
    read_s3_object,
    read_walrus_blob,
    storage_adapter_from_config,
    walrus_blob_id,
)


class _Response:
    status_code = 200

    def json(self):
        return {
            'newlyCreated': {
                'blobObject': {
                    'blobId': 'blob-123',
                    'id': 'object-123',
                }
            }
        }


class _Session:
    def __init__(self):
        self.calls = []

    def put(self, url, data, headers, timeout):
        self.calls.append({'url': url, 'data': data, 'headers': headers, 'timeout': timeout})
        return _Response()


class _ReadResponse:
    status_code = 200
    content = b'encrypted-bytes'


class _ReadSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout):
        self.calls.append({'url': url, 'timeout': timeout})
        return _ReadResponse()


class _S3Body:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class _S3Client:
    def __init__(self):
        self.put_calls = []
        self.get_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        return {'Body': _S3Body(b's3-encrypted-bytes')}


class _DriveCreateRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _DriveFiles:
    def __init__(self):
        self.create_calls = []
        self.get_media_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return _DriveCreateRequest({'id': 'drive-file-123'})

    def get_media(self, **kwargs):
        self.get_media_calls.append(kwargs)
        return _DriveCreateRequest(b'drive-encrypted-bytes')


class _DriveService:
    def __init__(self):
        self._files = _DriveFiles()

    def files(self):
        return self._files


def _encrypted():
    return encrypt_chunk_payload(
        {'data': '72'},
        key=b'\x08' * 32,
        nonce=b'\x09' * 24,
    )


def test_local_chunk_storage_adapter_writes_encrypted_file(tmp_path):
    encrypted = _encrypted()
    adapter = LocalChunkStorageAdapter(tmp_path)

    stored = adapter.store('sha256:abc', encrypted)

    assert stored.provider == 'file'
    assert stored.status == 'local'
    assert stored.storage_ref.startswith('file://')
    assert stored.local_path.endswith('abc.bin')
    assert stored.metadata == {}


def test_walrus_chunk_storage_adapter_uploads_ciphertext_after_local_write(tmp_path):
    encrypted = _encrypted()
    session = _Session()
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'chunk_storage_path': str(tmp_path),
                'storage': {
                    'backend': 'walrus',
                    'walrus': {
                        'publisher_url': 'https://publisher.example',
                        'aggregator_url': 'https://aggregator.example',
                        'publisher_token': 'token',
                        'epochs': 2,
                        'permanent': False,
                        'timeout_sec': 3,
                    },
                },
            }
        }
    )
    adapter = WalrusChunkStorageAdapter(cfg.expanded_chunk_storage_path, cfg.storage.walrus, session=session)

    stored = adapter.store('sha256:def', encrypted)

    assert stored.storage_ref == 'walrus://blob-123'
    assert stored.provider == 'walrus'
    assert stored.status == 'uploaded'
    assert stored.local_path.endswith('def.bin')
    assert stored.metadata['localStorageRef'].startswith('file://')
    assert stored.metadata['objectId'] == 'object-123'
    assert stored.metadata['aggregatorUrl'] == 'https://aggregator.example'
    assert session.calls[0]['url'] == 'https://publisher.example/v1/blobs?epochs=2&deletable=true'
    assert session.calls[0]['data'] == encrypted.ciphertext_bytes
    assert session.calls[0]['headers']['authorization'] == 'Bearer token'
    assert session.calls[0]['timeout'] == 3


def test_walrus_blob_id_accepts_already_certified_response():
    assert walrus_blob_id({'alreadyCertified': {'blobId': 'blob-certified'}}) == 'blob-certified'


def test_s3_chunk_storage_adapter_uploads_ciphertext_after_local_write(tmp_path):
    encrypted = _encrypted()
    s3_client = _S3Client()
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'chunk_storage_path': str(tmp_path),
                'storage': {
                    'backend': 's3',
                    's3': {
                        'bucket': 'stream-bucket',
                        'prefix': 'machine-1/chunks',
                        'endpoint_url': 'https://s3.example',
                        'region': 'eu-central-1',
                    },
                },
            }
        }
    )
    adapter = S3ChunkStorageAdapter(cfg.expanded_chunk_storage_path, cfg.storage.s3, client=s3_client)

    stored = adapter.store('sha256:1234', encrypted)

    assert stored.storage_ref == 's3://stream-bucket/machine-1/chunks/1234.bin'
    assert stored.provider == 's3'
    assert stored.status == 'uploaded'
    assert stored.local_path.endswith('1234.bin')
    assert stored.metadata['endpointUrl'] == 'https://s3.example'
    assert stored.metadata['localStorageRef'].startswith('file://')
    assert s3_client.put_calls[0]['Bucket'] == 'stream-bucket'
    assert s3_client.put_calls[0]['Key'] == 'machine-1/chunks/1234.bin'
    assert s3_client.put_calls[0]['Body'] == encrypted.ciphertext_bytes
    assert s3_client.put_calls[0]['Metadata']['encrypted-data-hash'] == encrypted.encrypted_data_hash


def test_read_walrus_blob_fetches_bytes_from_aggregator():
    session = _ReadSession()

    data = read_walrus_blob('https://aggregator.example/', 'blob-123', session=session, timeout=4)

    assert data == b'encrypted-bytes'
    assert session.calls == [{'url': 'https://aggregator.example/v1/blobs/blob-123', 'timeout': 4}]


def test_read_s3_object_fetches_bytes_from_storage_ref():
    client = _S3Client()

    data = read_s3_object('s3://stream-bucket/machine-1/chunks/1234.bin', client=client)

    assert data == b's3-encrypted-bytes'
    assert client.get_calls == [{'Bucket': 'stream-bucket', 'Key': 'machine-1/chunks/1234.bin'}]


def test_read_s3_object_uses_stream_env_for_s3_compatible_clients(monkeypatch):
    class _Boto3:
        def __init__(self):
            self.calls = []
            self.client_instance = _S3Client()

        def client(self, name, **kwargs):
            self.calls.append({'name': name, 'kwargs': kwargs})
            return self.client_instance

    fake_boto3 = _Boto3()
    monkeypatch.setitem(sys.modules, 'boto3', fake_boto3)
    monkeypatch.setenv('PEAQOS_STREAM_S3_ENDPOINT_URL', 'https://s3.example')
    monkeypatch.setenv('PEAQOS_STREAM_S3_REGION', 'eu-central-1')
    monkeypatch.setenv('PEAQOS_STREAM_S3_ACCESS_KEY_ID', 'access-key')
    monkeypatch.setenv('PEAQOS_STREAM_S3_SECRET_ACCESS_KEY', 'secret-key')

    data = read_s3_object('s3://stream-bucket/machine-1/chunks/1234.bin')

    assert data == b's3-encrypted-bytes'
    assert fake_boto3.calls == [
        {
            'name': 's3',
            'kwargs': {
                'endpoint_url': 'https://s3.example',
                'region_name': 'eu-central-1',
                'aws_access_key_id': 'access-key',
                'aws_secret_access_key': 'secret-key',
            },
        }
    ]
    assert fake_boto3.client_instance.get_calls == [{'Bucket': 'stream-bucket', 'Key': 'machine-1/chunks/1234.bin'}]


def test_google_drive_chunk_storage_adapter_uploads_ciphertext_after_local_write(tmp_path):
    encrypted = _encrypted()
    service = _DriveService()
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'chunk_storage_path': str(tmp_path),
                'storage': {
                    'backend': 'google-drive',
                    'google_drive': {'folder_id': 'folder-1'},
                },
            }
        }
    )
    adapter = GoogleDriveChunkStorageAdapter(
        cfg.expanded_chunk_storage_path,
        cfg.storage.google_drive,
        service=service,
    )

    stored = adapter.store('sha256:abcd', encrypted)

    assert stored.storage_ref == 'gdrive://drive-file-123'
    assert stored.provider == 'google-drive'
    assert stored.status == 'uploaded'
    assert stored.local_path.endswith('abcd.bin')
    assert stored.metadata['localStorageRef'].startswith('file://')
    call = service.files().create_calls[0]
    assert call['body']['name'] == 'abcd.bin'
    assert call['body']['parents'] == ['folder-1']
    assert call['media_body'] == encrypted.ciphertext_bytes


def test_read_google_drive_file_fetches_bytes():
    service = _DriveService()

    data = read_google_drive_file('drive-file-123', service=service)

    assert data == b'drive-encrypted-bytes'
    assert service.files().get_media_calls == [{'fileId': 'drive-file-123'}]


def test_storage_adapter_from_config_uses_local_by_default(tmp_path):
    cfg = load_stream_agent_config_from_dict({'stream_agent': {'chunk_storage_path': str(tmp_path)}})

    adapter = storage_adapter_from_config(cfg)

    assert isinstance(adapter, LocalChunkStorageAdapter)


def test_storage_adapter_from_config_uses_s3_when_selected(tmp_path):
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'chunk_storage_path': str(tmp_path),
                'storage': {
                    'backend': 's3',
                    's3': {'bucket': 'stream-bucket'},
                },
            }
        }
    )

    adapter = storage_adapter_from_config(cfg)

    assert isinstance(adapter, S3ChunkStorageAdapter)


def test_storage_adapter_from_config_uses_google_drive_when_selected(tmp_path):
    cfg = load_stream_agent_config_from_dict(
        {
            'stream_agent': {
                'chunk_storage_path': str(tmp_path),
                'storage': {
                    'backend': 'google-drive',
                    'google_drive': {'folder_id': 'folder-1'},
                },
            }
        }
    )

    adapter = storage_adapter_from_config(cfg)

    assert isinstance(adapter, GoogleDriveChunkStorageAdapter)
