"""ROS 2 node that signs configured topic data for peaqOS Stream."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message

from peaq_ros2_interfaces.srv import PeaqosSubmitEvent

from .api import StreamApiClient, StreamApiError
from .buffer import StreamEventBuffer
from .chunk_catalog import StreamChunkCatalog, record_from_manifest
from .chunk_keys import StreamChunkKeyStore
from .chunk_manifest import build_buyer_access, build_signed_chunk_manifest
from .chunk_storage import append_manifest, deterministic_chunk_id, last_manifest_chunk_id
from .config import StreamAgentConfig, TopicRule, load_stream_agent_config_from_params
from .crypto import load_or_create_signing_key, sign_envelope
from .delivery_server import StreamDeliveryServer
from .encryption import encrypt_chunk_payload
from .envelope import build_unsigned_envelope, utc_now_iso
from .qos import ros_qos_profile_for_rule
from .sequence import SequenceStore
from .storage_adapters import storage_adapter_from_config
from .transform import apply_field_rules, canonical_message_dict, extract_source_timestamp


class StreamAgentNode(Node):
    def __init__(self) -> None:
        super().__init__('stream_agent_node')
        self._declare_parameters()
        self.cfg = load_stream_agent_config_from_params(self._collect_non_default_params())
        self._subscriptions = []
        self._policy_id = ''
        self._policy_version = 0
        self._signing_key_id = ''
        self._previous_chunk_id: str | None = None
        self.delivery_server: StreamDeliveryServer | None = None

        if not self.cfg.enabled:
            self.get_logger().warn('stream_agent is disabled')
            return

        self.api = StreamApiClient(self.cfg.api_base_url, api_key=self.cfg.api_key)
        self.signing_key = load_or_create_signing_key(self.cfg.expanded_signing_key_path)
        self.buffer = StreamEventBuffer(
            self.cfg.buffer.expanded_path,
            max_events=self.cfg.buffer.max_events,
            retention_seconds=self.cfg.buffer.retention_seconds,
            retry_interval_seconds=self.cfg.buffer.retry_interval_seconds,
            overflow=self.cfg.buffer.overflow,
        )
        self.sequences = SequenceStore(self.cfg.expanded_sequence_state_path)
        self.catalog = StreamChunkCatalog(self.cfg.expanded_chunk_catalog_path)
        self.chunk_keys = StreamChunkKeyStore(self.cfg.expanded_chunk_key_store_path)
        self.chunk_store = storage_adapter_from_config(self.cfg)
        self._previous_chunk_id = last_manifest_chunk_id(self.cfg.expanded_chunk_manifest_path)
        self._peaqos_event_client = None
        if self.cfg.peaqos_event.enabled:
            self._peaqos_event_client = self.create_client(
                PeaqosSubmitEvent,
                f'/{self.cfg.peaqos_event.node_name}/events/submit',
            )

        self._sync_policy_and_key()
        if self.cfg.delivery.enabled:
            self.delivery_server = StreamDeliveryServer(
                self.catalog,
                self.cfg.expanded_chunk_manifest_path,
                self.cfg.delivery.token,
                host=self.cfg.delivery.host,
                port=self.cfg.delivery.port,
            )
            self.delivery_server.start()
            host, port = self.delivery_server.address
            self.get_logger().info(f'stream delivery API listening on {host}:{port}')
            self.create_timer(self.cfg.delivery.poll_interval_seconds, self._poll_delivery_sessions)
        self.create_timer(self.cfg.delivery.poll_interval_seconds, self._poll_paid_orders)
        self._create_topic_subscriptions()
        self.create_timer(self.cfg.buffer.retry_interval_seconds, self._retry_buffer)
        self.create_timer(self.cfg.heartbeat_interval_seconds, self._heartbeat)
        self._heartbeat()
        self.get_logger().info('stream_agent_node ready')

    def _declare_parameters(self) -> None:
        self.declare_parameter('config.yaml_path', '')
        self.declare_parameter('stream_agent.enabled', False)
        self.declare_parameter('stream_agent.api_base_url', '')
        self.declare_parameter('stream_agent.api_key', '')
        self.declare_parameter('stream_agent.machine_id', '')
        self.declare_parameter('stream_agent.agent_id', '')
        self.declare_parameter('stream_agent.agent_token', '')
        self.declare_parameter('stream_agent.identity_ref', '')
        self.declare_parameter('stream_agent.policy_path', '')
        self.declare_parameter('stream_agent.signing_key_path', '')
        self.declare_parameter('stream_agent.sequence_state_path', '')
        self.declare_parameter('stream_agent.chunk_storage_path', '')
        self.declare_parameter('stream_agent.chunk_manifest_path', '')
        self.declare_parameter('stream_agent.chunk_catalog_path', '')
        self.declare_parameter('stream_agent.chunk_key_store_path', '')
        self.declare_parameter('stream_agent.delivery_enabled', False)
        self.declare_parameter('stream_agent.delivery_host', '')
        self.declare_parameter('stream_agent.delivery_port', 0)
        self.declare_parameter('stream_agent.delivery_token', '')
        self.declare_parameter('stream_agent.delivery_poll_interval_seconds', 0)

    def _collect_non_default_params(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, parameter in self._parameters.items():
            value = parameter.value
            if value not in ('', False, 0):
                values[name] = value
        return values

    def _sync_policy_and_key(self) -> None:
        policy_payload = self.cfg.policy_payload()
        existing = next(
            (
                item
                for item in self.api.list_policies(self.cfg.machine_id)
                if item.get('name') == self.cfg.policy_name and item.get('status') != 'archived'
            ),
            None,
        )
        if existing:
            policy = self.api.update_policy(self.cfg.machine_id, str(existing['id']), policy_payload)
        else:
            policy = self.api.create_policy(self.cfg.machine_id, policy_payload)
        self._policy_id = str(policy['id'])
        self._policy_version = int(policy['version'])
        self._signing_key_id = f'{self.cfg.agent_id}-stream-ed25519'
        self.api.register_signing_key(
            self.cfg.machine_id,
            self.cfg.agent_id,
            self.cfg.agent_token,
            self._signing_key_id,
            self.signing_key.public_key_hex,
        )

    def _create_topic_subscriptions(self) -> None:
        discovered = {
            topic: set(types)
            for topic, types in self.get_topic_names_and_types()
        }
        for rule in self.cfg.topics:
            if rule.topic in discovered and rule.message_type not in discovered[rule.topic]:
                self.get_logger().warn(
                    f'{rule.topic} is live but does not advertise configured type {rule.message_type}'
                )
            try:
                message_type = get_message(rule.message_type)
            except Exception as exc:
                self.get_logger().error(f'failed to resolve message type {rule.message_type}: {exc}')
                continue
            subscription = self.create_subscription(
                message_type,
                rule.topic,
                lambda message, topic_rule=rule: self._handle_message(topic_rule, message),
                ros_qos_profile_for_rule(rule),
            )
            self._subscriptions.append(subscription)
            self.get_logger().info(f'streaming {rule.topic} as {rule.message_type}')

    def _handle_message(self, rule: TopicRule, message: Any) -> None:
        agent_received_at = utc_now_iso()
        try:
            canonical = canonical_message_dict(message_to_ordereddict(message))
        except Exception:
            canonical = canonical_message_dict(message)
        source_timestamp = extract_source_timestamp(canonical if isinstance(canonical, dict) else {})
        transformed = apply_field_rules(canonical if isinstance(canonical, dict) else {'data': canonical}, rule.field_rules)
        sequence_number = self.sequences.next(self.cfg.machine_id, rule.topic, self._policy_version)
        unsigned = build_unsigned_envelope(
            self.cfg,
            rule,
            self._policy_id,
            self._policy_version,
            sequence_number,
            transformed,
            source_timestamp,
            agent_received_at,
        )
        envelope = sign_envelope(unsigned, self.signing_key, self._signing_key_id)
        self._create_and_post_chunk(rule, transformed, sequence_number, source_timestamp, agent_received_at)
        try:
            self._send_envelope(envelope)
        except Exception as exc:
            self.buffer.enqueue(envelope)
            self.get_logger().warn(f'stream event buffered after send failure: {exc}')

    def _create_and_post_chunk(
        self,
        rule: TopicRule,
        payload: dict[str, Any],
        sequence_number: int,
        source_timestamp: str | None,
        agent_received_at: str,
    ) -> dict[str, Any] | None:
        try:
            encrypted = encrypt_chunk_payload(payload)
            chunk_id = deterministic_chunk_id(
                self._previous_chunk_id,
                sequence_number,
                encrypted.plaintext_hash,
                encrypted.encrypted_data_hash,
            )
            stored = self.chunk_store.store(chunk_id, encrypted)
            manifest = build_signed_chunk_manifest(
                self.cfg,
                encrypted,
                self.signing_key,
                self._signing_key_id,
                chunk_id=chunk_id,
                storage_ref=stored.storage_ref,
                previous_chunk_id=self._previous_chunk_id,
                index=sequence_number,
            )
            append_manifest(self.cfg.expanded_chunk_manifest_path, manifest)
            self.chunk_keys.put(str(manifest['chunkId']), encrypted.key_hex)
            try:
                self.catalog.upsert(
                    record_from_manifest(
                        manifest,
                        machine_id=self.cfg.machine_id,
                        agent_id=self.cfg.agent_id,
                        topic=rule.topic,
                        message_type=rule.message_type,
                        policy_id=self._policy_id,
                        policy_version=self._policy_version,
                        sequence_number=sequence_number,
                        source_timestamp=source_timestamp,
                        agent_received_at=agent_received_at,
                        manifest_path=self.cfg.expanded_chunk_manifest_path,
                        local_path=stored.local_path,
                        storage_provider=stored.provider,
                        status=stored.status,
                    )
                )
            except Exception as exc:
                self.get_logger().warn(f'stream chunk catalog update failed: {exc}')
            self._previous_chunk_id = str(manifest['chunkId'])
        except Exception as exc:
            self.get_logger().warn(f'stream chunk creation failed: {exc}')
            return None

        try:
            self.api.post_chunk(
                self.cfg.machine_id,
                self.cfg.agent_id,
                self.cfg.agent_token,
                manifest,
                metadata={
                    'topic': rule.topic,
                    'messageType': rule.message_type,
                    'policyId': self._policy_id,
                    'policyVersion': self._policy_version,
                    'sequenceNumber': sequence_number,
                    'sourceTimestamp': source_timestamp,
                    'agentReceivedAt': agent_received_at,
                    'observedAt': source_timestamp or agent_received_at,
                    'storageProvider': stored.provider,
                    'sizeBytes': len(encrypted.ciphertext_bytes),
                    'status': stored.status,
                },
            )
        except Exception as exc:
            self.get_logger().warn(f'stream chunk receipt failed: {exc}')
        return manifest

    def _send_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        receipt = self.api.post_event(self.cfg.agent_token, envelope)
        self._submit_chain_receipt(receipt)
        return receipt

    def _retry_buffer(self) -> None:
        for event in self.buffer.due(limit=25):
            try:
                self._send_envelope(event.envelope)
                self.buffer.mark_sent(event.id)
            except Exception as exc:
                self.buffer.record_failure(event.id)
                self.get_logger().warn(f'stream buffered event retry failed: {exc}')

    def _heartbeat(self) -> None:
        try:
            self.api.heartbeat(self.cfg.machine_id, self.cfg.agent_id, self.cfg.agent_token, self._policy_id)
        except StreamApiError as exc:
            self.get_logger().warn(f'stream heartbeat failed: {exc}')

    def _poll_delivery_sessions(self) -> None:
        if not self.delivery_server:
            return
        try:
            sessions = self.api.poll_delivery_sessions(
                self.cfg.machine_id,
                self.cfg.agent_id,
                self.cfg.agent_token,
                statuses=['requested'],
            )
        except Exception as exc:
            self.get_logger().warn(f'stream delivery session poll failed: {exc}')
            return

        delivery_url = self._delivery_base_url()
        for session in sessions:
            session_id = str(session.get('id') or '')
            chunk_ids = [str(item) for item in session.get('chunkIds', []) if str(item)]
            if not session_id or not chunk_ids:
                continue
            missing = [chunk_id for chunk_id in chunk_ids if not self._has_local_chunk(chunk_id)]
            if missing:
                self.get_logger().warn(f'stream delivery session {session_id} is waiting on local chunk {missing[0]}')
                continue
            delivery = session.get('delivery') if isinstance(session.get('delivery'), dict) else {}
            access_token = str(delivery.get('accessToken') or '')
            if access_token:
                self.delivery_server.allow_token(access_token)
            try:
                self.api.update_delivery_session(
                    session_id,
                    self.cfg.machine_id,
                    self.cfg.agent_id,
                    self.cfg.agent_token,
                    'ready',
                    delivery_url=delivery_url,
                    message='local delivery API ready',
                )
            except Exception as exc:
                self.get_logger().warn(f'stream delivery session update failed: {exc}')

    def _poll_paid_orders(self) -> None:
        try:
            orders = self.api.list_machine_orders(self.cfg.machine_id)
        except Exception as exc:
            self.get_logger().warn(f'stream order poll failed: {exc}')
            return

        for order in orders:
            if str(order.get('status') or '') != 'paid':
                continue
            order_id = str(order.get('id') or '')
            buyer_id = str(order.get('buyerId') or '')
            buyer_public_key_hex = str(order.get('buyerPublicKeyHex') or '').removeprefix('0x').lower()
            chunk_ids = [str(item) for item in order.get('chunkIds', []) if str(item)]
            if not order_id or not buyer_id or not buyer_public_key_hex or not chunk_ids:
                continue
            access_items = []
            missing_key = ''
            for chunk_id in chunk_ids:
                key_hex = self.chunk_keys.get(chunk_id)
                if not key_hex:
                    missing_key = chunk_id
                    break
                access_items.append(build_buyer_access(chunk_id, key_hex, buyer_id, buyer_public_key_hex))
            if missing_key:
                self.get_logger().warn(f'stream order {order_id} is waiting on chunk key {missing_key}')
                continue

            delivery = self._delivery_payload_for_order(chunk_ids)
            try:
                self.api.prepare_order_access(
                    order_id,
                    self.cfg.machine_id,
                    self.cfg.agent_id,
                    self.cfg.agent_token,
                    access_items,
                    delivery=delivery,
                )
                self.get_logger().info(f'stream order {order_id} buyer access prepared')
            except Exception as exc:
                self.get_logger().warn(f'stream order {order_id} access preparation failed: {exc}')

    def _delivery_payload_for_order(self, chunk_ids: list[str]) -> dict[str, str]:
        first_record = self.catalog.get(chunk_ids[0]) if chunk_ids else None
        provider = first_record.storage_provider if first_record else 'local'
        if provider == 'file':
            provider = 'local'
        payload = {'mode': provider if provider in {'local', 'walrus', 's3', 'google-drive'} else 'local'}
        if payload['mode'] == 'local' and self.delivery_server:
            payload['url'] = self._delivery_base_url()
            payload['message'] = 'local delivery API ready'
        return payload

    def _has_local_chunk(self, chunk_id: str) -> bool:
        record = self.catalog.get(chunk_id)
        return bool(record and record.local_path and Path(record.local_path).exists())

    def _delivery_base_url(self) -> str:
        if not self.delivery_server:
            return ''
        host, port = self.delivery_server.address
        advertised_host = self.cfg.delivery.host
        if advertised_host in {'', '0.0.0.0', '::'}:
            advertised_host = host
        return f'http://{advertised_host}:{port}'

    def _submit_chain_receipt(self, receipt: dict[str, Any]) -> None:
        if not self._peaqos_event_client or not self.cfg.peaqos_event.enabled:
            return
        if not self._peaqos_event_client.wait_for_service(timeout_sec=self.cfg.peaqos_event.service_wait_sec):
            self.get_logger().warn('peaqOS event submit service is not available')
            return
        data_hash = str(receipt.get('payloadHash', '')).replace('sha256:', '')
        if len(data_hash) != 64:
            return

        request = PeaqosSubmitEvent.Request()
        request.signer_address = ''
        request.machine_id = int(self.cfg.peaqos_event.machine_id)
        request.event_type = int(self.cfg.peaqos_event.event_type)
        request.value = 0
        request.timestamp = int(time.time())
        request.raw_data_hex = '0x' + data_hash
        request.trust_level = int(self.cfg.peaqos_event.trust_level)
        request.source_chain_id = int(self.cfg.peaqos_event.source_chain_id)
        request.source_tx_hash = ''
        metadata = {
            'streamReceiptId': receipt.get('id'),
            'policyId': receipt.get('policyId'),
            'policyVersion': receipt.get('policyVersion'),
        }
        request.metadata_hex = '0x' + json.dumps(metadata, separators=(',', ':')).encode('utf8').hex()

        future = self._peaqos_event_client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=self.cfg.peaqos_event.timeout_sec)
        result = future.result()
        if not result or not result.success:
            self.get_logger().warn(f'peaqOS event submit failed: {getattr(result, "error", "unknown")}')
            return
        self.api.patch_chain_receipt(
            str(receipt['id']),
            self.cfg.machine_id,
            self.cfg.agent_id,
            self.cfg.agent_token,
            result.tx_hash,
            result.data_hash,
        )

    def destroy_node(self) -> bool:
        if self.delivery_server:
            self.delivery_server.stop()
            self.delivery_server = None
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = StreamAgentNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
