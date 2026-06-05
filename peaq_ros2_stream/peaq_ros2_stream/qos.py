"""QoS preset mapping for Stream topic subscriptions."""

from __future__ import annotations

from dataclasses import dataclass

from .config import TopicRule


@dataclass(frozen=True)
class QoSProfileSpec:
    reliability: str
    durability: str
    history: str
    depth: int


def qos_spec_for_rule(rule: TopicRule) -> QoSProfileSpec:
    depth = rule.depth or (5 if rule.qos_preset == 'sensor_data' else 10)
    if rule.qos_preset == 'sensor_data':
        return QoSProfileSpec(
            reliability='best_effort',
            durability='volatile',
            history='keep_last',
            depth=depth,
        )
    return QoSProfileSpec(
        reliability='reliable',
        durability='volatile',
        history='keep_last',
        depth=depth,
    )


def ros_qos_profile_for_rule(rule: TopicRule):
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

    spec = qos_spec_for_rule(rule)
    reliability = ReliabilityPolicy.BEST_EFFORT if spec.reliability == 'best_effort' else ReliabilityPolicy.RELIABLE
    durability = DurabilityPolicy.VOLATILE
    history = HistoryPolicy.KEEP_LAST
    return QoSProfile(depth=spec.depth, reliability=reliability, durability=durability, history=history)
