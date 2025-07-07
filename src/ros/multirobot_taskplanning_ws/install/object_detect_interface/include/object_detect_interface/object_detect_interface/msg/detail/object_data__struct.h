// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from object_detect_interface:msg/ObjectData.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_H_
#define OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'pose'
#include "geometry_msgs/msg/detail/pose__struct.h"

/// Struct defined in msg/ObjectData in the package object_detect_interface.
/**
  * ArUco 마커의 id 와 Pose 정보를 전달하는 메시지
 */
typedef struct object_detect_interface__msg__ObjectData
{
  int16_t id;
  geometry_msgs__msg__Pose pose;
} object_detect_interface__msg__ObjectData;

// Struct for a sequence of object_detect_interface__msg__ObjectData.
typedef struct object_detect_interface__msg__ObjectData__Sequence
{
  object_detect_interface__msg__ObjectData * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} object_detect_interface__msg__ObjectData__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_H_
