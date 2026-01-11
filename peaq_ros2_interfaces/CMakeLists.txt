cmake_minimum_required(VERSION 3.8)
project(peaq_ros2_interfaces)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)

# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)

set(msg_files
  "msg/TxStatus.msg"
  "msg/Event.msg"
  "msg/StorageIngest.msg"
  "msg/StorageResult.msg"
)

set(srv_files
  "srv/IdentityCreate.srv"
  "srv/IdentityRead.srv"
  "srv/StoreAddData.srv"
  "srv/StoreReadData.srv"
  "srv/AccessCreateRole.srv"
  "srv/AccessCreatePermission.srv"
  "srv/AccessAssignPermToRole.srv"
  "srv/AccessGrantRole.srv"
  "srv/GetNodeInfo.srv"
  "srv/TetherCreateWallet.srv"
  "srv/TetherGetUsdtBalance.srv"
  "srv/TetherTransferUsdt.srv"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES builtin_interfaces
  ADD_LINTER_TESTS
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment in if your copyright lines are too long.
  # set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment in if your generated cpp files are not in git
  # set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
