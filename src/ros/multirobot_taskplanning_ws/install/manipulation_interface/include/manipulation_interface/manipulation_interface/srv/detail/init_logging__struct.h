// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from manipulation_interface:srv/InitLogging.idl
// generated code does not contain a copyright notice

#ifndef MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__STRUCT_H_
#define MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

/// Struct defined in srv/InitLogging in the package manipulation_interface.
typedef struct manipulation_interface__srv__InitLogging_Request
{
  int16_t object_id;
  int16_t action_id;
} manipulation_interface__srv__InitLogging_Request;

// Struct for a sequence of manipulation_interface__srv__InitLogging_Request.
typedef struct manipulation_interface__srv__InitLogging_Request__Sequence
{
  manipulation_interface__srv__InitLogging_Request * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} manipulation_interface__srv__InitLogging_Request__Sequence;


// Constants defined in the message

/// Struct defined in srv/InitLogging in the package manipulation_interface.
typedef struct manipulation_interface__srv__InitLogging_Response
{
  bool success;
} manipulation_interface__srv__InitLogging_Response;

// Struct for a sequence of manipulation_interface__srv__InitLogging_Response.
typedef struct manipulation_interface__srv__InitLogging_Response__Sequence
{
  manipulation_interface__srv__InitLogging_Response * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} manipulation_interface__srv__InitLogging_Response__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__STRUCT_H_
