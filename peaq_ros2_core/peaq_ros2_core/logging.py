"""
Structured logging for peaq ROS 2 core package.
Provides human-readable logs with optional JSON format.
"""
import json
import logging
from typing import Dict, Any
from datetime import datetime
from .config import PeaqRosConfig


class PeaqRosFormatter(logging.Formatter):
    """Custom formatter for peaq ROS 2 logs."""

    def __init__(self, config: PeaqRosConfig):
        super().__init__()
        self.config = config
        self.is_json = config.log_format == 'json'

    def format(self, record: logging.LogRecord) -> str:
        """Format log record based on configuration."""
        if self.is_json:
            return self._format_json(record)
        else:
            return self._format_human(record)

    def _format_human(self, record: logging.LogRecord) -> str:
        """Format log in human-readable format."""
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Add emoji based on log level
        level_emojis = {
            'DEBUG': '🔍',
            'INFO': '📋',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }
        emoji = level_emojis.get(record.levelname, '📝')

        # Format message
        if hasattr(record, 'robot_data'):
            # Special formatting for robot data
            return f"{timestamp} {emoji} [{record.levelname}] {record.getMessage()} | {record.robot_data}"
        else:
            return f"{timestamp} {emoji} [{record.levelname}] {record.getMessage()}"

    def _format_json(self, record: logging.LogRecord) -> str:
        """Format log in JSON format."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        if hasattr(record, 'robot_data'):
            log_data['robot_data'] = record.robot_data

        return json.dumps(log_data)


def setup_logging(config: PeaqRosConfig) -> logging.Logger:
    """Set up logging for peaq ROS 2 core."""
    logger = logging.getLogger('peaq_ros2_core')
    logger.setLevel(getattr(logging, config.log_level))

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler()
    handler.setFormatter(PeaqRosFormatter(config))
    logger.addHandler(handler)

    return logger


def log_transaction_status(logger: logging.Logger, phase: str, tx_hash: str = None,
                          block: int = 0, error: str = None, robot_data: Dict[str, Any] = None):
    """Log transaction status with structured format."""
    message = f"Transaction {phase}"
    if tx_hash:
        message += f" | Hash: {tx_hash[:8]}..."
    if block > 0:
        message += f" | Block: {block}"
    if error:
        message += f" | Error: {error}"

    extra_data = {}
    if robot_data:
        extra_data['robot_data'] = robot_data

    logger.info(message, extra=extra_data)


def log_event(logger: logging.Logger, source: str, event_type: str, payload: Dict[str, Any] = None):
    """Log blockchain event with structured format."""
    message = f"Event from {source}: {event_type}"
    if payload:
        # Include key payload info in message for human readability
        key_items = []
        for key, value in list(payload.items())[:3]:  # Limit to first 3 items
            if isinstance(value, (str, int, float, bool)):
                key_items.append(f"{key}={value}")
        if key_items:
            message += f" | {', '.join(key_items)}"

    robot_data = {
        'event_source': source,
        'event_type': event_type,
        'payload': payload
    } if payload else {
        'event_source': source,
        'event_type': event_type
    }

    logger.info(message, extra={'robot_data': robot_data})


def log_identity_operation(logger: logging.Logger, operation: str, name: str = None,
                          tx_hash: str = None, success: bool = True):
    """Log identity operations."""
    status = "✅" if success else "❌"
    message = f"Identity {operation} {status}"
    if name:
        message += f" | Name: {name}"
    if tx_hash:
        message += f" | Tx: {tx_hash[:8]}..."

    logger.info(message)


def log_storage_operation(logger: logging.Logger, operation: str, key: str,
                         mode: str = None, tx_hash: str = None, success: bool = True):
    """Log storage operations."""
    status = "✅" if success else "❌"
    message = f"Storage {operation} {status} | Key: {key}"
    if mode:
        message += f" | Mode: {mode}"
    if tx_hash:
        message += f" | Tx: {tx_hash[:8]}..."

    logger.info(message)


def log_access_operation(logger: logging.Logger, operation: str, target: str,
                        tx_hash: str = None, success: bool = True):
    """Log access control operations."""
    status = "✅" if success else "❌"
    message = f"Access {operation} {status} | Target: {target}"
    if tx_hash:
        message += f" | Tx: {tx_hash[:8]}..."

    logger.info(message)
