"""
Core ROS 2 node providing blockchain services over peaq_robot SDK.

This node exposes identity, storage, and access control services as ROS 2 services
and publishes transaction status updates.
"""
import os
import json
import time
import random
import rclpy
from rclpy.node import Node
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn
from rcl_interfaces.msg import ParameterDescriptor

# Import peaq_robot SDK
from peaq_robot import PeaqRobot

# Import custom interfaces
from peaq_ros2_interfaces.srv import (
    IdentityCreate,
    IdentityRead,
    StoreAddData,
    StoreReadData,
    AccessCreateRole,
    AccessCreatePermission,
    AccessAssignPermToRole,
    AccessGrantRole,
    GetNodeInfo,
)
from peaq_ros2_interfaces.msg import TxStatus

# Import local modules
from .config import PeaqRosConfig, load_config_from_params
from .logging import setup_logging, log_transaction_status, log_identity_operation, log_storage_operation, log_access_operation


class CoreNode(LifecycleNode):
    """Lifecycle-managed core node providing blockchain services."""

    def __init__(self, node_name: str = 'peaq_core_node'):
        super().__init__(node_name)

        # Declare parameters
        self.declare_parameter('config.yaml_path', '')
        self.declare_parameter('network', 'agung')
        self.declare_parameter('keystore.path', '')
        self.declare_parameter('log_level', 'INFO')

        # Initialize configuration
        self.config = None
        self.logger = None
        self.robot_sdk = None

        # Service servers (will be created in configure state)
        self._identity_create_service = None
        self._identity_read_service = None
        self._store_add_service = None
        self._store_read_service = None
        self._access_create_role_service = None
        self._access_create_permission_service = None
        self._access_assign_perm_service = None
        self._access_grant_role_service = None
        self._get_node_info_service = None

        # Publishers
        self._tx_status_publisher = None

        # Optional autostart without lifecycle transitions (for dev/offline mode)
        if os.getenv('PEAQ_ROS2_AUTOSTART', 'false').lower() == 'true':
            try:
                self._autostart_setup()
            except Exception as e:
                self.get_logger().error(f'Autostart setup failed: {str(e)}')

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Configure the node with parameters and initialize SDK."""
        self.get_logger().info('Configuring peaq core node...')

        try:
            # Load configuration from parameters
            params = {}
            for param_name in self._parameters.keys():
                params[param_name] = self.get_parameter(param_name).value

            self.config = load_config_from_params(params)
            self.logger = setup_logging(self.config)

            # Initialize peaq robot SDK
            self._initialize_robot_sdk()

            # Create service servers
            self._create_service_servers()

            # Create publishers
            self._create_publishers()

            self.logger.info('✅ Core node configured successfully')
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f'Failed to configure node: {str(e)}')
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Activate the node."""
        self.get_logger().info('Activating peaq core node...')
        self.logger.info('🚀 Core node activated')
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Deactivate the node."""
        self.get_logger().info('Deactivating peaq core node...')
        self.logger.info('⏸️ Core node deactivated')
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Clean up the node."""
        self.get_logger().info('Cleaning up peaq core node...')

        # Clean up services
        if self._identity_create_service:
            self.destroy_service(self._identity_create_service)
        if self._identity_read_service:
            self.destroy_service(self._identity_read_service)
        if self._store_add_service:
            self.destroy_service(self._store_add_service)
        if self._store_read_service:
            self.destroy_service(self._store_read_service)
        if self._access_create_role_service:
            self.destroy_service(self._access_create_role_service)
        if self._access_create_permission_service:
            self.destroy_service(self._access_create_permission_service)
        if self._access_assign_perm_service:
            self.destroy_service(self._access_assign_perm_service)
        if self._get_node_info_service:
            self.destroy_service(self._get_node_info_service)
        if self._access_grant_role_service:
            self.destroy_service(self._access_grant_role_service)

        # Clean up publishers
        if self._tx_status_publisher:
            self.destroy_publisher(self._tx_status_publisher)

        self.logger.info('🧹 Core node cleaned up')
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        """Shutdown the node."""
        self.get_logger().info('Shutting down peaq core node...')
        self.logger.info('👋 Core node shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _initialize_robot_sdk(self):
        """Initialize the peaq robot SDK."""
        try:
            # Get keystore password from environment
            password = self.config.keystore_password

            # Handle auto-generate wallet
            keystore_path = self.config.keystore_path
            if self.config.keystore_auto_generate:
                keystore_path = self._handle_auto_generate_wallet(keystore_path)

            # Offline mode to avoid network access during local dev/testing
            if os.getenv('PEAQ_ROBOT_OFFLINE', 'false').lower() == 'true':
                self.robot_sdk = self._create_mock_robot_sdk()
            else:
                self.robot_sdk = PeaqRobot(
                    network=self.config.network_url,
                    keystore_path=keystore_path
                )

            self.logger.info(f'🔑 Core node wallet address: {self.robot_sdk.address}')

            # Set password if provided
            if password:
                # Note: This is a simplified approach. In production,
                # you might need to handle keystore unlocking differently
                self.logger.info('🔑 Keystore password provided via environment')

            self.logger.info(f'🔗 Connected to {self.config.network} network')

        except Exception as e:
            error_msg = f'Failed to initialize robot SDK: {str(e)}'
            self.get_logger().error(error_msg)
            raise RuntimeError(error_msg)

    def _handle_auto_generate_wallet(self, wallet_path: str) -> str:
        """Handle auto-generate wallet logic.
        
        If wallet exists: use it (log warning)
        If wallet doesn't exist: generate new one
        
        Returns the wallet path to use.
        """
        expanded_path = os.path.expanduser(wallet_path)
        
        if os.path.exists(expanded_path):
            self.logger.warning(
                f'auto_generate=true but wallet already exists at {expanded_path}. '
                f'Using existing wallet. To regenerate, delete the file first.'
            )
            return expanded_path
        
        # Generate new wallet
        self.logger.info(f'Generating new wallet at {expanded_path}...')
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
        
        # Generate using PeaqRobot (it will auto-generate and save)
        from peaq_robot import PeaqRobot
        temp_robot = PeaqRobot(
            network=self.config.network_url,
            keystore_path=expanded_path
        )
        
        self.logger.info(f'✅ New wallet generated at {expanded_path}')
        self.logger.info(f'   Address: {temp_robot.address}')
        
        return expanded_path

    def _create_mock_robot_sdk(self):
        """Create a minimal mock of the peaq_robot SDK for offline testing."""
        class _MockIdentity:
            def __init__(self, outer):
                self._outer = outer

            def create_identity(self, name: str, metadata: str, confirmation_mode: str) -> str:
                return _MockRobotSDK._gen_tx()

            def read_identity(self):
                return {
                    'did': 'did:peaq:offline',
                    'name': 'offline_identity',
                    'metadata': {'mode': 'offline'},
                }

        class _MockStore:
            def __init__(self, outer):
                self._outer = outer
                self._db = {}

            # Mirror PyPI signature add_data(data_type, data, *, tx_options=None, on_status=None)
            def add_data(self, data_type: str, data: dict, **kwargs) -> str:
                self._db[data_type] = data
                return _MockRobotSDK._gen_tx()

            def read_data(self, data_type: str):
                return self._db.get(data_type, {})

        class _MockAccess:
            def __init__(self, outer):
                self._outer = outer

            def create_role(self, role: str, description: str, confirmation_mode: str) -> str:
                return _MockRobotSDK._gen_tx()

            def create_permission(self, permission: str, description: str, confirmation_mode: str) -> str:
                return _MockRobotSDK._gen_tx()

            def assign_permission_to_role(self, permission: str, role: str, confirmation_mode: str) -> str:
                return _MockRobotSDK._gen_tx()

            def grant_role(self, role: str, user: str, confirmation_mode: str) -> str:
                return _MockRobotSDK._gen_tx()

        class _MockRobotSDK:
            def __init__(self, outer):
                self.id = _MockIdentity(outer)
                self.store = _MockStore(outer)
                self.access = _MockAccess(outer)

            @staticmethod
            def _gen_tx() -> str:
                # 0x + 64 hex
                return f"0x{random.getrandbits(256):064x}"

        return _MockRobotSDK(self)

    def _autostart_setup(self):
        """Initialize config, logging, SDK, services and publishers without lifecycle."""
        # Use defaults/env when launching without lifecycle transitions
        self.config = PeaqRosConfig()
        self.logger = setup_logging(self.config)
        self._initialize_robot_sdk()
        self._create_service_servers()
        self._create_publishers()
        self.logger.info('⚙️ Autostart completed (services and publishers ready)')

    def _create_service_servers(self):
        """Create ROS 2 service servers."""
        # Identity services
        self._identity_create_service = self.create_service(
            IdentityCreate,
            '~/identity/create',
            self._handle_identity_create
        )

        self._identity_read_service = self.create_service(
            IdentityRead,
            '~/identity/read',
            self._handle_identity_read
        )

        # Storage services
        self._store_add_service = self.create_service(
            StoreAddData,
            '~/storage/add',
            self._handle_store_add
        )

        self._store_read_service = self.create_service(
            StoreReadData,
            '~/storage/read',
            self._handle_store_read
        )

        # Access control services
        self._access_create_role_service = self.create_service(
            AccessCreateRole,
            '~/access/create_role',
            self._handle_access_create_role
        )

        self._access_create_permission_service = self.create_service(
            AccessCreatePermission,
            '~/access/create_permission',
            self._handle_access_create_permission
        )

        self._access_assign_perm_service = self.create_service(
            AccessAssignPermToRole,
            '~/access/assign_permission',
            self._handle_access_assign_permission
        )

        self._access_grant_role_service = self.create_service(
            AccessGrantRole,
            '~/access/grant_role',
            self._handle_access_grant_role
        )

        # Node info service
        self._get_node_info_service = self.create_service(
            GetNodeInfo,
            '~/info',
            self._handle_get_node_info
        )

        self.logger.info('📡 Service servers created')

    def _create_publishers(self):
        """Create ROS 2 publishers."""
        self._tx_status_publisher = self.create_publisher(
            TxStatus,
            'peaq/tx_status',
            10
        )

        self.logger.info('📢 Publishers created')

    def _handle_identity_create(self, request, response):
        """Handle identity creation requests."""
        try:
            # Auto-derive DID name from wallet address
            did_name = f'did:peaq:{self.robot_sdk.address}'
            self.logger.info(f'Creating identity: {did_name}')

            # Create identity using SDK
            tx_hash = self.robot_sdk.id.create_identity(
                name=did_name,
                metadata=request.metadata_json,
                confirmation_mode=self.config.default_confirmation_mode
            )

            response.tx_hash = tx_hash

            # Log success
            log_identity_operation(self.logger, 'created', did_name, tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Identity creation initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to create identity: {str(e)}'
            self.logger.error(error_msg)
            response.tx_hash = ''
            did_name = f'did:peaq:{self.robot_sdk.address}'
            log_identity_operation(self.logger, 'creation_failed', did_name, success=False)

        return response

    def _handle_identity_read(self, request, response):
        """Handle identity read requests."""
        try:
            self.logger.info('Reading identity document')

            # Read identity using SDK
            doc = self.robot_sdk.id.read_identity()

            response.doc_json = json.dumps(doc, indent=2)

            log_identity_operation(self.logger, 'read', success=True)
            self.logger.info('✅ Identity document retrieved')

        except Exception as e:
            error_msg = f'Failed to read identity: {str(e)}'
            self.logger.error(error_msg)
            response.doc_json = '{}'
            log_identity_operation(self.logger, 'read_failed', success=False)

        return response

    def _handle_store_add(self, request, response):
        """Handle storage add requests."""
        try:
            self.logger.info(f'Adding data to storage: {request.key}')

            # Parse value JSON
            try:
                value_data = json.loads(request.value_json)
            except json.JSONDecodeError as e:
                raise ValueError(f'Invalid JSON in value: {str(e)}')

            # Add data using SDK (PyPI peaq-robot-sdk signature: add_data(data_type, data, *, tx_options=None, on_status=None))
            tx_hash = self.robot_sdk.store.add_data(
                request.key,
                value_data,
            )

            response.result = f'Success: {tx_hash}'

            # Log success
            log_storage_operation(self.logger, 'added', request.key, request.mode, tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Data storage initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to add storage data: {str(e)}'
            self.logger.error(error_msg)
            response.result = f'Error: {error_msg}'
            log_storage_operation(self.logger, 'add_failed', request.key, request.mode, success=False)

        return response

    def _handle_store_read(self, request, response):
        """Handle storage read requests."""
        try:
            self.logger.info(f'Reading data from storage: {request.key}')

            # Read data using SDK
            data = self.robot_sdk.store.read_data(request.key)

            response.value_json = json.dumps(data, indent=2)

            log_storage_operation(self.logger, 'read', request.key, success=True)
            self.logger.info('✅ Storage data retrieved')

        except Exception as e:
            error_msg = f'Failed to read storage data: {str(e)}'
            self.logger.error(error_msg)
            response.value_json = '{}'
            log_storage_operation(self.logger, 'read_failed', request.key, success=False)

        return response

    def _handle_access_create_role(self, request, response):
        """Handle role creation requests."""
        try:
            self.logger.info(f'Creating role: {request.role}')

            # Create role using SDK (PyPI signature: (role_name, description=''))
            tx_hash = self.robot_sdk.access.create_role(
                request.role,
                request.description,
            )

            response.tx_hash = tx_hash

            # Log success
            log_access_operation(self.logger, 'role_created', request.role, tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Role creation initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to create role: {str(e)}'
            self.logger.error(error_msg)
            response.tx_hash = ''
            log_access_operation(self.logger, 'role_creation_failed', request.role, success=False)

        return response

    def _handle_access_create_permission(self, request, response):
        """Handle permission creation requests."""
        try:
            self.logger.info(f'Creating permission: {request.permission}')

            # Create permission using SDK (PyPI signature: (permission_name, description=''))
            tx_hash = self.robot_sdk.access.create_permission(
                request.permission,
                request.description,
            )

            response.tx_hash = tx_hash

            # Log success
            log_access_operation(self.logger, 'permission_created', request.permission, tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Permission creation initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to create permission: {str(e)}'
            self.logger.error(error_msg)
            response.tx_hash = ''
            log_access_operation(self.logger, 'permission_creation_failed', request.permission, success=False)

        return response

    def _handle_access_assign_permission(self, request, response):
        """Handle permission assignment requests."""
        try:
            self.logger.info(f'Assigning permission {request.permission} to role {request.role}')

            # Assign permission using SDK (PyPI signature: (permission_name, role_name))
            tx_hash = self.robot_sdk.access.assign_permission_to_role(
                request.permission,
                request.role,
            )

            response.tx_hash = tx_hash

            # Log success
            log_access_operation(self.logger, 'permission_assigned', f'{request.permission}→{request.role}', tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Permission assignment initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to assign permission: {str(e)}'
            self.logger.error(error_msg)
            response.tx_hash = ''
            log_access_operation(self.logger, 'permission_assignment_failed', f'{request.permission}→{request.role}', success=False)

        return response

    def _handle_access_grant_role(self, request, response):
        """Handle role granting requests."""
        try:
            self.logger.info(f'Granting role {request.role} to user {request.user}')

            # Grant role using SDK (PyPI signature: (role_name, user_identifier))
            tx_hash = self.robot_sdk.access.grant_role(
                request.role,
                request.user,
            )

            response.tx_hash = tx_hash

            # Log success
            log_access_operation(self.logger, 'role_granted', f'{request.role}→{request.user}', tx_hash, success=True)

            # Publish transaction status
            self._publish_tx_status('PENDING', tx_hash)

            self.logger.info(f'✅ Role granting initiated: {tx_hash[:8]}...')

        except Exception as e:
            error_msg = f'Failed to grant role: {str(e)}'
            self.logger.error(error_msg)
            response.tx_hash = ''
            log_access_operation(self.logger, 'role_granting_failed', f'{request.role}→{request.user}', success=False)

        return response

    def _handle_get_node_info(self, request, response):
        """Handle node info requests - returns machine/node information."""
        try:
            self.logger.info('Getting node information')

            # Gather node information
            info = {
                'node_name': self.get_name(),
                'network': self.config.network if self.config else 'unknown',
                'network_url': self.config.network_url if self.config else 'unknown',
                'wallet_address': self.robot_sdk.keypair.ss58_address if self.robot_sdk else 'unknown',
                'public_key': self.robot_sdk.keypair.public_key.hex() if self.robot_sdk else 'unknown',
                'did': f"did:peaq:{self.robot_sdk.keypair.ss58_address}" if self.robot_sdk else 'unknown',
                'confirmation_mode': self.config.default_confirmation_mode if self.config else 'unknown',
                'log_level': self.config.log_level if self.config else 'unknown',
                'keystore_path': self.config.keystore_path if self.config else 'unknown',
                'events_enabled': self.config.events_enabled if self.config else False,
                'node_state': self._state_machine.current_state[1] if hasattr(self, '_state_machine') else 'unknown',
                'services': [
                    '/identity/create',
                    '/identity/read',
                    '/storage/add',
                    '/storage/read',
                    '/access/create_role',
                    '/access/create_permission',
                    '/access/assign_permission',
                    '/access/grant_role',
                    '/info'
                ],
                'topics': {
                    'tx_status': '/peaq/tx_status'
                }
            }

            response.result = json.dumps(info, indent=2)
            self.logger.info('✅ Node information retrieved')

        except Exception as e:
            error_msg = f'Failed to get node info: {str(e)}'
            self.logger.error(error_msg)
            response.result = json.dumps({'error': error_msg}, indent=2)

        return response

    def _publish_tx_status(self, phase: str, tx_hash: str, block: int = 0, error: str = None):
        """Publish transaction status to ROS topic."""
        if not self._tx_status_publisher:
            return

        msg = TxStatus()
        msg.phase = phase
        msg.tx_hash = tx_hash
        msg.block = block
        msg.error = error or ''

        self._tx_status_publisher.publish(msg)


def main(args=None):
    """Main entry point for the core node."""
    rclpy.init(args=args)

    # Create node with lifecycle management
    node = CoreNode()

    try:
        # Spin the node
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
