// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_H_
#define OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/DetectObjects in the package object_detect_interface.
typedef struct object_detect_interface__srv__DetectObjects_Request
{
  uint8_t structure_needs_at_least_one_member;
} object_detect_interface__srv__DetectObjects_Request;

// Struct for a sequence of object_detect_interface__srv__DetectObjects_Request.
typedef struct object_detect_interface__srv__DetectObjects_Request__Sequence
{
  object_detect_interface__srv__DetectObjects_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} object_detect_interface__srv__DetectObjects_Request__Sequence;


// Constants defined in the message

// Include directives for member types
// Member 'object_list'
#include "object_detect_interface/msg/detail/object_data__struct.h"

/// Struct defined in srv/DetectObjects in the package object_detect_interface.
typedef struct object_detect_interface__srv__DetectObjects_Response
{
  int16_t entity_num;
  object_detect_interface__msg__ObjectData__Sequence object_list;
} object_detect_interface__srv__DetectObjects_Response;

// Struct for a sequence of object_detect_interface__srv__DetectObjects_Response.
typedef struct object_detect_interface__srv__DetectObjects_Response__Sequence
{
  object_detect_interface__srv__DetectObjects_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} object_detect_interface__srv__DetectObjects_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_H_
