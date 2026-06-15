"""Encrypted chunk storage adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

import requests

from .chunk_storage import chunk_file_name
from .encryption import EncryptedChunk
from .models import GoogleDriveStorageConfig, S3StorageConfig, StreamAgentConfig, WalrusStorageConfig


@dataclass(frozen=True)
class StoredChunk:
    storage_ref: str
    local_path: str
    provider: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ChunkStorageAdapter(Protocol):
    def store(self, chunk_id: str, encrypted: EncryptedChunk) -> StoredChunk:
        ...


class LocalChunkStorageAdapter:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser()

    def store(self, chunk_id: str, encrypted: EncryptedChunk) -> StoredChunk:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / chunk_file_name(chunk_id)
        path.write_bytes(encrypted.ciphertext_bytes)
        resolved = path.resolve()
        return StoredChunk(
            storage_ref=resolved.as_uri(),
            local_path=str(resolved),
            provider='file',
            status='local',
        )


class WalrusChunkStorageAdapter:
    def __init__(
        self,
        directory: str | Path,
        walrus: WalrusStorageConfig,
        session: requests.Session | None = None,
    ) -> None:
        self.local = LocalChunkStorageAdapter(directory)
        self.walrus = walrus
        self.session = session or requests.Session()

    def store(self, chunk_id: str, encrypted: EncryptedChunk) -> StoredChunk:
        local = self.local.store(chunk_id, encrypted)
        publisher_url = self.walrus.publisher_url.rstrip('/')
        if not publisher_url:
            raise ValueError('Walrus publisher URL is required when stream storage backend is walrus')

        query_key = 'permanent' if self.walrus.permanent else 'deletable'
        url = f'{publisher_url}/v1/blobs?epochs={max(1, int(self.walrus.epochs))}&{query_key}=true'
        headers = {'content-type': 'application/octet-stream'}
        if self.walrus.publisher_token:
            headers['authorization'] = f'Bearer {self.walrus.publisher_token}'
        response = self.session.put(
            url,
            data=encrypted.ciphertext_bytes,
            headers=headers,
            timeout=max(1.0, float(self.walrus.timeout_sec)),
        )
        if response.status_code >= 400:
            raise RuntimeError(f'Walrus chunk upload failed: HTTP {response.status_code}')
        payload = response.json()
        blob_id = walrus_blob_id(payload)
        if not blob_id:
            raise RuntimeError('Walrus publisher response did not include blobId')
        aggregator_url = self.walrus.aggregator_url.rstrip('/')
        return StoredChunk(
            storage_ref=f'walrus://{blob_id}',
            local_path=local.local_path,
            provider='walrus',
            status='uploaded',
            metadata={
                'blobId': blob_id,
                'objectId': walrus_object_id(payload),
                'publisherUrl': publisher_url,
                'aggregatorUrl': aggregator_url,
                'localStorageRef': local.storage_ref,
            },
        )


class S3ChunkStorageAdapter:
    def __init__(
        self,
        directory: str | Path,
        s3: S3StorageConfig,
        client: Any | None = None,
    ) -> None:
        self.local = LocalChunkStorageAdapter(directory)
        self.s3 = s3
        self.client = client

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        try:
            import boto3  # type: ignore
        except Exception as exc:
            raise RuntimeError('boto3 is required when stream storage backend is s3') from exc

        kwargs: dict[str, Any] = {}
        if self.s3.endpoint_url:
            kwargs['endpoint_url'] = self.s3.endpoint_url
        if self.s3.region:
            kwargs['region_name'] = self.s3.region
        if self.s3.access_key_id:
            kwargs['aws_access_key_id'] = self.s3.access_key_id
        if self.s3.secret_access_key:
            kwargs['aws_secret_access_key'] = self.s3.secret_access_key
        if self.s3.session_token:
            kwargs['aws_session_token'] = self.s3.session_token
        self.client = boto3.client('s3', **kwargs)
        return self.client

    def store(self, chunk_id: str, encrypted: EncryptedChunk) -> StoredChunk:
        local = self.local.store(chunk_id, encrypted)
        bucket = self.s3.bucket.strip()
        if not bucket:
            raise ValueError('S3 bucket is required when stream storage backend is s3')
        prefix = self.s3.prefix.strip().strip('/')
        key = f'{prefix}/{chunk_file_name(chunk_id)}' if prefix else chunk_file_name(chunk_id)
        self._client().put_object(
            Bucket=bucket,
            Key=key,
            Body=encrypted.ciphertext_bytes,
            ContentType='application/octet-stream',
            Metadata={
                'chunk-id': chunk_id,
                'encrypted-data-hash': encrypted.encrypted_data_hash,
            },
        )
        return StoredChunk(
            storage_ref=f's3://{bucket}/{key}',
            local_path=local.local_path,
            provider='s3',
            status='uploaded',
            metadata={
                'bucket': bucket,
                'key': key,
                'endpointUrl': self.s3.endpoint_url,
                'localStorageRef': local.storage_ref,
            },
        )


class GoogleDriveChunkStorageAdapter:
    def __init__(
        self,
        directory: str | Path,
        drive: GoogleDriveStorageConfig,
        service: Any | None = None,
    ) -> None:
        self.local = LocalChunkStorageAdapter(directory)
        self.drive = drive
        self.service = service
        self._service_provided = service is not None

    def _service(self) -> Any:
        if self.service is not None:
            return self.service
        try:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
        except Exception as exc:
            raise RuntimeError('Google Drive libraries are required when stream storage backend is google-drive') from exc
        if not self.drive.credentials_path:
            raise ValueError('Google Drive credentials_path is required when stream storage backend is google-drive')
        credentials = service_account.Credentials.from_service_account_file(
            str(Path(self.drive.credentials_path).expanduser()),
            scopes=['https://www.googleapis.com/auth/drive.file'],
        )
        self.service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
        return self.service

    def _media_body(self, encrypted: EncryptedChunk) -> Any:
        if self._service_provided:
            return encrypted.ciphertext_bytes
        try:
            from googleapiclient.http import MediaIoBaseUpload  # type: ignore
        except Exception as exc:
            raise RuntimeError('Google Drive media upload support is required') from exc
        return MediaIoBaseUpload(
            BytesIO(encrypted.ciphertext_bytes),
            mimetype='application/octet-stream',
            resumable=False,
        )

    def store(self, chunk_id: str, encrypted: EncryptedChunk) -> StoredChunk:
        local = self.local.store(chunk_id, encrypted)
        folder_id = self.drive.folder_id.strip()
        if not folder_id:
            raise ValueError('Google Drive folder_id is required when stream storage backend is google-drive')
        file_name = chunk_file_name(chunk_id)
        payload = (
            self._service()
            .files()
            .create(
                body={
                    'name': file_name,
                    'parents': [folder_id],
                    'mimeType': 'application/octet-stream',
                    'description': f'peaq Stream encrypted chunk {chunk_id}',
                },
                media_body=self._media_body(encrypted),
                fields='id',
            )
            .execute()
        )
        file_id = str(payload.get('id') or '')
        if not file_id:
            raise RuntimeError('Google Drive upload response did not include file id')
        return StoredChunk(
            storage_ref=f'gdrive://{file_id}',
            local_path=local.local_path,
            provider='google-drive',
            status='uploaded',
            metadata={
                'fileId': file_id,
                'folderId': folder_id,
                'localStorageRef': local.storage_ref,
            },
        )


def storage_adapter_from_config(cfg: StreamAgentConfig) -> ChunkStorageAdapter:
    if cfg.storage.backend == 'walrus':
        return WalrusChunkStorageAdapter(cfg.expanded_chunk_storage_path, cfg.storage.walrus)
    if cfg.storage.backend == 's3':
        return S3ChunkStorageAdapter(cfg.expanded_chunk_storage_path, cfg.storage.s3)
    if cfg.storage.backend == 'google-drive':
        return GoogleDriveChunkStorageAdapter(cfg.expanded_chunk_storage_path, cfg.storage.google_drive)
    return LocalChunkStorageAdapter(cfg.expanded_chunk_storage_path)


def walrus_blob_id(payload: dict[str, Any]) -> str:
    created = payload.get('newlyCreated') or payload.get('newly_created') or {}
    certified = payload.get('alreadyCertified') or payload.get('already_certified') or {}
    blob_object = created.get('blobObject') or created.get('blob_object') or {}
    return str(
        blob_object.get('blobId')
        or blob_object.get('blob_id')
        or certified.get('blobId')
        or certified.get('blob_id')
        or ''
    )


def walrus_object_id(payload: dict[str, Any]) -> str:
    created = payload.get('newlyCreated') or payload.get('newly_created') or {}
    blob_object = created.get('blobObject') or created.get('blob_object') or {}
    return str(blob_object.get('id') or blob_object.get('objectId') or blob_object.get('object_id') or '')


def read_walrus_blob(
    aggregator_url: str,
    blob_id: str,
    session: requests.Session | None = None,
    timeout: float = 10.0,
) -> bytes:
    base_url = aggregator_url.rstrip('/')
    if not base_url:
        raise ValueError('Walrus aggregator URL is required to read a blob')
    if not blob_id:
        raise ValueError('Walrus blob id is required to read a blob')
    response = (session or requests.Session()).get(
        f'{base_url}/v1/blobs/{blob_id}',
        timeout=max(1.0, float(timeout)),
    )
    if response.status_code >= 400:
        raise RuntimeError(f'Walrus blob read failed: HTTP {response.status_code}')
    return bytes(response.content)


def read_s3_object(storage_ref: str, client: Any | None = None) -> bytes:
    if not storage_ref.startswith('s3://'):
        raise ValueError('S3 storageRef must start with s3://')
    path = storage_ref.removeprefix('s3://')
    bucket, _, key = path.partition('/')
    if not bucket or not key:
        raise ValueError('S3 storageRef must include bucket and key')
    if client is None:
        try:
            import boto3  # type: ignore
        except Exception as exc:
            raise RuntimeError('boto3 is required to read S3 stream chunks') from exc
        kwargs: dict[str, Any] = {}
        endpoint_url = (
            os.getenv('PEAQOS_STREAM_S3_ENDPOINT_URL')
            or os.getenv('AWS_ENDPOINT_URL_S3')
            or os.getenv('AWS_ENDPOINT_URL')
        )
        region = os.getenv('PEAQOS_STREAM_S3_REGION') or os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')
        access_key_id = os.getenv('PEAQOS_STREAM_S3_ACCESS_KEY_ID') or os.getenv('AWS_ACCESS_KEY_ID')
        secret_access_key = os.getenv('PEAQOS_STREAM_S3_SECRET_ACCESS_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY')
        session_token = os.getenv('PEAQOS_STREAM_S3_SESSION_TOKEN') or os.getenv('AWS_SESSION_TOKEN')
        if endpoint_url:
            kwargs['endpoint_url'] = endpoint_url
        if region:
            kwargs['region_name'] = region
        if access_key_id:
            kwargs['aws_access_key_id'] = access_key_id
        if secret_access_key:
            kwargs['aws_secret_access_key'] = secret_access_key
        if session_token:
            kwargs['aws_session_token'] = session_token
        client = boto3.client('s3', **kwargs)
    response = client.get_object(Bucket=bucket, Key=key)
    body = response.get('Body')
    if body is None:
        raise RuntimeError('S3 response did not include a body')
    return bytes(body.read())


def read_google_drive_file(file_id: str, service: Any | None = None, credentials_path: str = '') -> bytes:
    if not file_id:
        raise ValueError('Google Drive file id is required')
    if service is None:
        try:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
        except Exception as exc:
            raise RuntimeError('Google Drive libraries are required to read Stream chunks') from exc
        if not credentials_path:
            raise ValueError('Google Drive credentials_path is required')
        credentials = service_account.Credentials.from_service_account_file(
            str(Path(credentials_path).expanduser()),
            scopes=['https://www.googleapis.com/auth/drive.readonly'],
        )
        service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    payload = service.files().get_media(fileId=file_id).execute()
    return bytes(payload)
