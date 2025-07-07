// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from robotiq_gripper_interface:srv/GetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__STRUCT_H_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/GetGripperStateCommand in the package robotiq_gripper_interface.
typedef struct robotiq_gripper_interface__srv__GetGripperStateCommand_Request
{
  uint8_t structure_needs_at_least_one_member;
} robotiq_gripper_interface__srv__GetGripperStateCommand_Request;

// Struct for a sequence of robotiq_gripper_interface__srv__GetGripperStateCommand_Request.
typedef struct robotiq_gripper_interface__srv__GetGripperStateCommand_Request__Sequence
{
  robotiq_gripper_interface__srv__GetGripperStateCommand_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robotiq_gripper_interface__srv__GetGripperStateCommand_Request__Sequence;


// Constants defined in the message

/// Struct defined in srv/GetGripperStateCommand in the package robotiq_gripper_interface.
typedef struct robotiq_gripper_interface__srv__GetGripperStateCommand_Response
{
  float position;
  float speed;
  float force;
} robotiq_gripper_interface__srv__GetGripperStateCommand_Response;

// Struct for a sequence of robotiq_gripper_interface__srv__GetGripperStateCommand_Response.
typedef struct robotiq_gripper_interface__srv__GetGripperStateCommand_Response__Sequence
{
  robotiq_gripper_interface__srv__GetGripperStateCommand_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robotiq_gripper_interface__srv__GetGripperStateCommand_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__STRUCT_H_
