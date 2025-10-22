#!/usr/bin/env python3
import inspect
from peaq_robot.access import RobotAccess
from peaq_robot.identity import RobotIdentity

def main():
    print('create_role:', inspect.signature(RobotAccess.create_role))
    print('create_permission:', inspect.signature(RobotAccess.create_permission))
    print('assign_permission_to_role:', inspect.signature(RobotAccess.assign_permission_to_role))
    print('grant_role:', inspect.signature(RobotAccess.grant_role))
    print('identity.create_identity:', inspect.signature(RobotIdentity.create_identity))
    print('identity.read_identity:', inspect.signature(RobotIdentity.read_identity))

if __name__ == '__main__':
    main()


