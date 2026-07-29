cmake_minimum_required(VERSION 3.8)
project(ramp_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/FailureStatus.msg"
  "msg/RecoveryDecision.msg"
  "msg/EpisodeEvent.msg"
  "srv/SelectRecovery.srv"
  "srv/ResetRecovery.srv"
  DEPENDENCIES builtin_interfaces geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
