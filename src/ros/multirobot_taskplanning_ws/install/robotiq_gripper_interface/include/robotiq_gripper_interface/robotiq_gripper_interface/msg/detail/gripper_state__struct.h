// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_H_
#define ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in msg/GripperState in the package robotiq_gripper_interface.
typedef struct robotiq_gripper_interface__msg__GripperState
{
  uint8_t g_act;
  uint8_t g_gto;
  uint8_t g_sta;
  uint8_t g_obj;
  uint8_t g_flt;
  uint8_t g_pr;
  uint8_t g_po;
  uint8_t g_cu;
} robotiq_gripper_interface__msg__GripperState;

// Struct for a sequence of robotiq_gripper_interface__msg__GripperState.
typedef struct robotiq_gripper_interface__msg__GripperState__Sequence
{
  robotiq_gripper_interface__msg__GripperState * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} robotiq_gripper_interface__msg__GripperState__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_H_
