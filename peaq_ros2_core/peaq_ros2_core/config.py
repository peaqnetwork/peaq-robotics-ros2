"""
Configuration management for peaq_ros2_core package.
Provides validated parameter parsing and defaults.
"""
import os
from typing import Optional
from dataclasses import dataclass, field

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:
    _HAS_YAML = False
def resolve_network_url(network: str) -> str:
    """Resolve a human-friendly network name to a websocket URL.

    Supports common aliases; returns the input if it already looks like a URL.
    """
    net = (network or '').strip()
    if net.startswith('ws://') or net.startswith('wss://'):
        return net
    mappings = {
        # Use OnFinality Agung endpoint for better compatibility
        'agung': 'wss://peaq-agung.api.onfinality.io/ws',
        'testnet': 'wss://peaq-agung.api.onfinality.io/ws',
        'peaq': 'wss://wss.mainnet.peaq.network',
        'mainnet': 'wss://wss.mainnet.peaq.network',
    }
    return mappings.get(net.lower(), net)


def get_default_keystore_path() -> str:
    """Return a sensible default keystore path under the user's home directory."""
    return os.path.expanduser('~/.peaq_robot/wallet.json')


@dataclass
class PeaqRosConfig:
    """Configuration for peaq ROS 2 core nodes."""

    # Network configuration
    network: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_NETWORK', 'agung'))

    # Confirmation mode for transactions
    default_confirmation_mode: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_CONFIRMATION_MODE', 'FAST'))

    # Keystore configuration
    keystore_path: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_KEYSTORE', get_default_keystore_path()))
    keystore_password_env: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_KEY_PASSWORD_ENV', 'PEAQ_ROBOT_KEY_PASSWORD'))
    keystore_auto_generate: bool = field(default=False)

    # Event streaming configuration
    events_enabled: bool = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_EVENTS_ENABLED', 'true').lower() == 'true')

    # Logging configuration
    log_level: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_LOG_LEVEL', 'INFO'))
    log_format: str = field(default_factory=lambda: os.getenv('PEAQ_ROBOT_LOG_FORMAT', 'human'))  # 'human' or 'json'

    # Node configuration
    node_name: str = field(default='peaq_core_node')
    events_node_name: str = field(default='peaq_events_node')

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate confirmation mode
        valid_modes = ['FAST', 'FINAL']
        if self.default_confirmation_mode not in valid_modes:
            raise ValueError(f"Invalid confirmation mode: {self.default_confirmation_mode}. Must be one of {valid_modes}")

        # Validate log level
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level not in valid_log_levels:
            raise ValueError(f"Invalid log level: {self.log_level}. Must be one of {valid_log_levels}")

        # Validate log format
        valid_log_formats = ['human', 'json']
        if self.log_format not in valid_log_formats:
            raise ValueError(f"Invalid log format: {self.log_format}. Must be one of {valid_log_formats}")

        # Resolve network URL
        self.network_url = resolve_network_url(self.network)

    @property
    def keystore_password(self) -> Optional[str]:
        """Get keystore password from environment variable."""
        return os.getenv(self.keystore_password_env)

    def to_dict(self) -> dict:
        """Convert configuration to dictionary for logging."""
        return {
            'network': self.network,
            'network_url': self.network_url,
            'default_confirmation_mode': self.default_confirmation_mode,
            'keystore_path': self.keystore_path,
            'keystore_password_env': self.keystore_password_env,
            'events_enabled': self.events_enabled,
            'log_level': self.log_level,
            'log_format': self.log_format,
            'node_name': self.node_name,
            'events_node_name': self.events_node_name,
        }


def load_config_from_params(params) -> PeaqRosConfig:
    """Load configuration from ROS 2 parameters."""
    config_dict = {}

    # Map ROS parameters to config fields
    param_mapping = {
        'network': 'network',
        'default_confirmation_mode': 'default_confirmation_mode',
        'keystore.path': 'keystore_path',
        'keystore.password_env': 'keystore_password_env',
        'events.enabled': 'events_enabled',
        'log_level': 'log_level',
        'log_format': 'log_format',
    }

    for param_key, config_key in param_mapping.items():
        if param_key in params:
            config_dict[config_key] = params[param_key]

    # Optional YAML overlay
    yaml_path = params.get('config.yaml_path') or os.getenv('PEAQ_ROS2_CONFIG_YAML', '')
    if yaml_path:
        if not _HAS_YAML:
            raise RuntimeError('PyYAML is required to load config.yaml_path')
        try:
            with open(os.path.expanduser(yaml_path), 'r') as f:
                data = yaml.safe_load(f) or {}
            
            # Support both old flat structure and new unified structure
            # New structure: core_node section for core-specific config
            core_config = data.get('core_node', {})
            
            # Network (shared, top-level)
            if 'network' in data:
                config_dict['network'] = data['network']
            
            # Logging (shared, can be top-level or nested)
            logging = data.get('logging', {})
            if 'log_level' in logging:
                config_dict['log_level'] = logging['log_level']
            elif 'log_level' in data:
                config_dict['log_level'] = data['log_level']
            
            if 'log_format' in logging:
                config_dict['log_format'] = logging['log_format']
            elif 'log_format' in data:
                config_dict['log_format'] = data['log_format']
            
            # Wallet (shared, top-level)
            wallet = data.get('wallet', {})
            if isinstance(wallet, dict):
                if 'path' in wallet:
                    config_dict['keystore_path'] = wallet['path']
                if 'password_env' in wallet:
                    config_dict['keystore_password_env'] = wallet['password_env']
                if 'auto_generate' in wallet:
                    config_dict['keystore_auto_generate'] = bool(wallet['auto_generate'])
            
            # Legacy keystore support (old structure)
            ks = data.get('keystore', {})
            if isinstance(ks, dict):
                if 'path' in ks:
                    config_dict['keystore_path'] = ks['path']
                if 'password_env' in ks:
                    config_dict['keystore_password_env'] = ks['password_env']
            
            # Core node specific config
            if 'confirmation_mode' in core_config:
                config_dict['default_confirmation_mode'] = core_config['confirmation_mode']
            elif 'default_confirmation_mode' in data:
                config_dict['default_confirmation_mode'] = data['default_confirmation_mode']
            
            # Events (core node specific)
            ev = core_config.get('events', data.get('events', {}))
            if isinstance(ev, dict) and 'enabled' in ev:
                config_dict['events_enabled'] = bool(ev['enabled'])
                
        except Exception as e:
            raise RuntimeError(f'Failed loading YAML config at {yaml_path}: {e}')

    return PeaqRosConfig(**config_dict)
