// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from franka_msgs:srv/ErrorRecovery.idl
// generated code does not contain a copyright notice

#ifndef FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__STRUCT_H_
#define FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/ErrorRecovery in the package franka_msgs.
typedef struct franka_msgs__srv__ErrorRecovery_Request
{
  uint8_t structure_needs_at_least_one_member;
} franka_msgs__srv__ErrorRecovery_Request;

// Struct for a sequence of franka_msgs__srv__ErrorRecovery_Request.
typedef struct franka_msgs__srv__ErrorRecovery_Request__Sequence
{
  franka_msgs__srv__ErrorRecovery_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} franka_msgs__srv__ErrorRecovery_Request__Sequence;


// Constants defined in the message

// Include directives for member types
// Member 'error'
#include "rosidl_runtime_c/string.h"

/// Struct defined in srv/ErrorRecovery in the package franka_msgs.
typedef struct franka_msgs__srv__ErrorRecovery_Response
{
  bool success;
  rosidl_runtime_c__String error;
} franka_msgs__srv__ErrorRecovery_Response;

// Struct for a sequence of franka_msgs__srv__ErrorRecovery_Response.
typedef struct franka_msgs__srv__ErrorRecovery_Response__Sequence
{
  franka_msgs__srv__ErrorRecovery_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} franka_msgs__srv__ErrorRecovery_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__STRUCT_H_
