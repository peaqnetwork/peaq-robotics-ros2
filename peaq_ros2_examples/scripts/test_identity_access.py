#!/usr/bin/env python3
import json
import time
import sys
import rclpy
from rclpy.node import Node

from peaq_ros2_interfaces.srv import (
    IdentityRead,
    IdentityCreate,
    AccessCreateRole,
    AccessCreatePermission,
    AccessAssignPermToRole,
    AccessGrantRole,
)
from peaq_ros2_interfaces.msg import TxStatus


class IdentityAccessTester(Node):
    def __init__(self) -> None:
        super().__init__('identity_access_tester')
        self.tx_statuses = []
        self.create_subscription(TxStatus, 'peaq/tx_status', self._on_tx, 10)

        self.identity_read = self.create_client(IdentityRead, '/peaq_core_node/identity/read')
        self.identity_create = self.create_client(IdentityCreate, '/peaq_core_node/identity/create')

        self.create_role = self.create_client(AccessCreateRole, '/peaq_core_node/access/create_role')
        self.create_permission = self.create_client(AccessCreatePermission, '/peaq_core_node/access/create_permission')
        self.assign_permission = self.create_client(AccessAssignPermToRole, '/peaq_core_node/access/assign_permission')
        self.grant_role = self.create_client(AccessGrantRole, '/peaq_core_node/access/grant_role')

    def _on_tx(self, msg: TxStatus) -> None:
        self.tx_statuses.append((msg.tx_hash, msg.phase, msg.block, msg.error))

    def _wait(self, fut, timeout=60.0):
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout)
        if not fut.done():
            raise RuntimeError('call timed out')
        return fut.result()

    def run(self) -> None:
        # Identity read
        if not self.identity_read.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('identity/read unavailable')
        res = self._wait(self.identity_read.call_async(IdentityRead.Request()), timeout=15.0)
        print('IDENTITY_READ_DOC:', (res.doc_json or '')[:200])

        # Identity create
        if not self.identity_create.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('identity/create unavailable')
        req = IdentityCreate.Request()
        req.name = f"robot_{int(time.time())}"
        req.metadata_json = json.dumps({'env': 'test'})
        tx = self._wait(self.identity_create.call_async(req), timeout=60.0).tx_hash
        print('IDENTITY_CREATE_TX:', tx)

        # Access: role + permission + assign + grant
        if not self.create_role.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('access/create_role unavailable')
        if not self.create_permission.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('access/create_permission unavailable')
        if not self.assign_permission.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('access/assign_permission unavailable')
        if not self.grant_role.wait_for_service(timeout_sec=10.0):
            raise RuntimeError('access/grant_role unavailable')

        role = f"viewer_{int(time.time())}"
        perm = f"read_{int(time.time())}"
        # create role
        rr = AccessCreateRole.Request(); rr.role = role; rr.description = 'viewer role'
        role_tx = self._wait(self.create_role.call_async(rr), timeout=60.0).tx_hash
        print('ACCESS_CREATE_ROLE_TX:', role_tx)
        # create permission
        rp = AccessCreatePermission.Request(); rp.permission = perm; rp.description = 'read perm'
        perm_tx = self._wait(self.create_permission.call_async(rp), timeout=60.0).tx_hash
        print('ACCESS_CREATE_PERMISSION_TX:', perm_tx)
        # assign permission to role
        ra = AccessAssignPermToRole.Request(); ra.permission = perm; ra.role = role
        assign_tx = self._wait(self.assign_permission.call_async(ra), timeout=60.0).tx_hash
        print('ACCESS_ASSIGN_PERMISSION_TX:', assign_tx)
        # grant role to self address placeholder (for demo use same role string)
        rg = AccessGrantRole.Request(); rg.role = role; rg.user = '5EFpYxMa5pKrKJfz6HW4E18putcQHaqUqxNskoumCXbkYsiD'
        grant_tx = self._wait(self.grant_role.call_async(rg), timeout=60.0).tx_hash
        print('ACCESS_GRANT_ROLE_TX:', grant_tx)

        # Print tx status snapshot
        print('TX_STATUS_EVENTS:', self.tx_statuses[-10:])


def main():
    rclpy.init()
    node = IdentityAccessTester()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())


