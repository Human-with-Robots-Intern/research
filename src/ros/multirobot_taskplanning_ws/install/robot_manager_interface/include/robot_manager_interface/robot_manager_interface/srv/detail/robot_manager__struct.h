// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from robot_manager_interface:srv/RobotManager.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_H_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/RobotManager in the package robot_manager_interface.
typedef struct robot_manager_interface__srv__RobotManager_Request
{
  int64_t robot_model;
  int64_t instruction;
  int64_t a;
  int64_t b;
} robot_manager_interface__srv__RobotManager_Request;

// Struct for a sequence of robot_manager_interface__srv__RobotManager_Request.
typedef struct robot_manager_interface__srv__RobotManager_Request__Sequence
{
  robot_manager_interface__srv__RobotManager_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robot_manager_interface__srv__RobotManager_Request__Sequence;


// Constants defined in the message

/// Struct defined in srv/RobotManager in the package robot_manager_interface.
typedef struct robot_manager_interface__srv__RobotManager_Response
{
  bool success;
} robot_manager_interface__srv__RobotManager_Response;

// Struct for a sequence of robot_manager_interface__srv__RobotManager_Response.
typedef struct robot_manager_interface__srv__RobotManager_Response__Sequence
{
  robot_manager_interface__srv__RobotManager_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robot_manager_interface__srv__RobotManager_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_H_
