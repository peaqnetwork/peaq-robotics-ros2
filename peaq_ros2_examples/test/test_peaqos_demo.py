"""Smoke test for the peaqOS example console module."""

from importlib import import_module
from pathlib import Path
import sys
import types


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_peaqos_demo_imports(monkeypatch) -> None:
    rclpy = types.ModuleType('rclpy')
    rclpy.init = lambda: None
    rclpy.shutdown = lambda: None
    rclpy.spin_until_future_complete = lambda *_args, **_kwargs: None

    rclpy_node = types.ModuleType('rclpy.node')
    rclpy_node.Node = type('Node', (), {})

    srv = types.ModuleType('peaq_ros2_interfaces.srv')
    srv.PeaqosCreateWallet = type('PeaqosCreateWallet', (), {})
    srv.PeaqosValidateEvent = type('PeaqosValidateEvent', (), {})

    monkeypatch.setitem(sys.modules, 'rclpy', rclpy)
    monkeypatch.setitem(sys.modules, 'rclpy.node', rclpy_node)
    monkeypatch.setitem(sys.modules, 'peaq_ros2_interfaces.srv', srv)

    module = import_module('peaq_ros2_examples.scripts.peaqos_demo')
    assert callable(module.main)
