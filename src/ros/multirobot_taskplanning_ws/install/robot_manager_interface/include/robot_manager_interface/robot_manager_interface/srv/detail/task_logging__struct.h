// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_H_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'sub_action'
#include "rosidl_runtime_c/string.h"

/// Struct defined in srv/TaskLogging in the package robot_manager_interface.
typedef struct robot_manager_interface__srv__TaskLogging_Request
{
  int16_t object_id_a;
  int16_t object_id_b;
  int16_t instruction;
  /// 기본 값 -1
  int16_t sequence_id;
  rosidl_runtime_c__String sub_action;
  bool relativity;
} robot_manager_interface__srv__TaskLogging_Request;

// Struct for a sequence of robot_manager_interface__srv__TaskLogging_Request.
typedef struct robot_manager_interface__srv__TaskLogging_Request__Sequence
{
  robot_manager_interface__srv__TaskLogging_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robot_manager_interface__srv__TaskLogging_Request__Sequence;


// Constants defined in the message

/// Struct defined in srv/TaskLogging in the package robot_manager_interface.
typedef struct robot_manager_interface__srv__TaskLogging_Response
{
  bool success;
} robot_manager_interface__srv__TaskLogging_Response;

// Struct for a sequence of robot_manager_interface__srv__TaskLogging_Response.
typedef struct robot_manager_interface__srv__TaskLogging_Response__Sequence
{
  robot_manager_interface__srv__TaskLogging_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robot_manager_interface__srv__TaskLogging_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_H_
