"""ROS 2 node that signs configured topic data for peaqOS Stream."""

from __future__ import annotations

import json
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rosidl_runtime_py.convert import message_to_ordereddict
from rosidl_runtime_py.utilities import get_message

from peaq_ros2_interfaces.srv import PeaqosSubmitEvent

from .api import StreamApiClient, StreamApiError
from .buffer import StreamEventBuffer
from .chunk_storage import append_manifest, build_and_store_chunk, last_manifest_chunk_id
from .config import StreamAgentConfig, TopicRule, load_stream_agent_config_from_params
from .crypto import load_or_create_signing_key, sign_envelope
from .encryption import encrypt_chunk_payload
from .envelope import build_unsigned_envelope, utc_now_iso
from .qos import ros_qos_profile_for_rule
from .sequence import SequenceStore
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
        self._previous_chunk_id = last_manifest_chunk_id(self.cfg.expanded_chunk_manifest_path)
        self._peaqos_event_client = None
        if self.cfg.peaqos_event.enabled:
            self._peaqos_event_client = self.create_client(
                PeaqosSubmitEvent,
                f'/{self.cfg.peaqos_event.node_name}/events/submit',
            )

        self._sync_policy_and_key()
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
        self._create_and_post_chunk(transformed, sequence_number)
        try:
            self._send_envelope(envelope)
        except Exception as exc:
            self.buffer.enqueue(envelope)
            self.get_logger().warn(f'stream event buffered after send failure: {exc}')

    def _create_and_post_chunk(self, payload: dict[str, Any], sequence_number: int) -> dict[str, Any] | None:
        try:
            encrypted = encrypt_chunk_payload(payload)
            manifest = build_and_store_chunk(
                self.cfg.expanded_chunk_storage_path,
                self.cfg,
                encrypted,
                self.signing_key,
                self._signing_key_id,
                previous_chunk_id=self._previous_chunk_id,
                index=sequence_number,
            )
            append_manifest(self.cfg.expanded_chunk_manifest_path, manifest)
            self._previous_chunk_id = str(manifest['chunkId'])
        except Exception as exc:
            self.get_logger().warn(f'stream chunk creation failed: {exc}')
            return None

        try:
            self.api.post_chunk(self.cfg.machine_id, self.cfg.agent_id, self.cfg.agent_token, manifest)
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
