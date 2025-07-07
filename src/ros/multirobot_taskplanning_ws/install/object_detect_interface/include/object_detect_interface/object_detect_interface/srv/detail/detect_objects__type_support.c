// generated from rosidl_typesupport_introspection_c/resource/idl__type_support.c.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#include <stddef.h>
#include "object_detect_interface/srv/detail/detect_objects__rosidl_typesupport_introspection_c.h"
#include "object_detect_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "object_detect_interface/srv/detail/detect_objects__functions.h"
#include "object_detect_interface/srv/detail/detect_objects__struct.h"


#ifdef __cplusplus
extern "C"
{
#endif

void object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  object_detect_interface__srv__DetectObjects_Request__init(message_memory);
}

void object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_fini_function(void * message_memory)
{
  object_detect_interface__srv__DetectObjects_Request__fini(message_memory);
}

static rosidl_typesupport_introspection_c__MessageMember object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_member_array[1] = {
  {
    "structure_needs_at_least_one_member",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT8,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface__srv__DetectObjects_Request, structure_needs_at_least_one_member),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_members = {
  "object_detect_interface__srv",  // message namespace
  "DetectObjects_Request",  // message name
  1,  // number of fields
  sizeof(object_detect_interface__srv__DetectObjects_Request),
  object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_member_array,  // message members
  object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_init_function,  // function to initialize message memory (memory has to be allocated)
  object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_type_support_handle = {
  0,
  &object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_object_detect_interface
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Request)() {
  if (!object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_type_support_handle.typesupport_identifier) {
    object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &object_detect_interface__srv__DetectObjects_Request__rosidl_typesupport_introspection_c__DetectObjects_Request_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif

// already included above
// #include <stddef.h>
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__rosidl_typesupport_introspection_c.h"
// already included above
// #include "object_detect_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
// already included above
// #include "rosidl_typesupport_introspection_c/field_types.h"
// already included above
// #include "rosidl_typesupport_introspection_c/identifier.h"
// already included above
// #include "rosidl_typesupport_introspection_c/message_introspection.h"
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__functions.h"
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__struct.h"


// Include directives for member types
// Member `object_list`
#include "object_detect_interface/msg/object_data.h"
// Member `object_list`
#include "object_detect_interface/msg/detail/object_data__rosidl_typesupport_introspection_c.h"

#ifdef __cplusplus
extern "C"
{
#endif

void object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  object_detect_interface__srv__DetectObjects_Response__init(message_memory);
}

void object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_fini_function(void * message_memory)
{
  object_detect_interface__srv__DetectObjects_Response__fini(message_memory);
}

size_t object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__size_function__DetectObjects_Response__object_list(
  const void * untyped_member)
{
  const object_detect_interface__msg__ObjectData__Sequence * member =
    (const object_detect_interface__msg__ObjectData__Sequence *)(untyped_member);
  return member->size;
}

const void * object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_const_function__DetectObjects_Response__object_list(
  const void * untyped_member, size_t index)
{
  const object_detect_interface__msg__ObjectData__Sequence * member =
    (const object_detect_interface__msg__ObjectData__Sequence *)(untyped_member);
  return &member->data[index];
}

void * object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_function__DetectObjects_Response__object_list(
  void * untyped_member, size_t index)
{
  object_detect_interface__msg__ObjectData__Sequence * member =
    (object_detect_interface__msg__ObjectData__Sequence *)(untyped_member);
  return &member->data[index];
}

void object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__fetch_function__DetectObjects_Response__object_list(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const object_detect_interface__msg__ObjectData * item =
    ((const object_detect_interface__msg__ObjectData *)
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_const_function__DetectObjects_Response__object_list(untyped_member, index));
  object_detect_interface__msg__ObjectData * value =
    (object_detect_interface__msg__ObjectData *)(untyped_value);
  *value = *item;
}

void object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__assign_function__DetectObjects_Response__object_list(
  void * untyped_member, size_t index, const void * untyped_value)
{
  object_detect_interface__msg__ObjectData * item =
    ((object_detect_interface__msg__ObjectData *)
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_function__DetectObjects_Response__object_list(untyped_member, index));
  const object_detect_interface__msg__ObjectData * value =
    (const object_detect_interface__msg__ObjectData *)(untyped_value);
  *item = *value;
}

bool object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__resize_function__DetectObjects_Response__object_list(
  void * untyped_member, size_t size)
{
  object_detect_interface__msg__ObjectData__Sequence * member =
    (object_detect_interface__msg__ObjectData__Sequence *)(untyped_member);
  object_detect_interface__msg__ObjectData__Sequence__fini(member);
  return object_detect_interface__msg__ObjectData__Sequence__init(member, size);
}

static rosidl_typesupport_introspection_c__MessageMember object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_member_array[2] = {
  {
    "entity_num",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface__srv__DetectObjects_Response, entity_num),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "object_list",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    NULL,  // members of sub message (initialized later)
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface__srv__DetectObjects_Response, object_list),  // bytes offset in struct
    NULL,  // default value
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__size_function__DetectObjects_Response__object_list,  // size() function pointer
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_const_function__DetectObjects_Response__object_list,  // get_const(index) function pointer
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__get_function__DetectObjects_Response__object_list,  // get(index) function pointer
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__fetch_function__DetectObjects_Response__object_list,  // fetch(index, &value) function pointer
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__assign_function__DetectObjects_Response__object_list,  // assign(index, value) function pointer
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__resize_function__DetectObjects_Response__object_list  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_members = {
  "object_detect_interface__srv",  // message namespace
  "DetectObjects_Response",  // message name
  2,  // number of fields
  sizeof(object_detect_interface__srv__DetectObjects_Response),
  object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_member_array,  // message members
  object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_init_function,  // function to initialize message memory (memory has to be allocated)
  object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_type_support_handle = {
  0,
  &object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_object_detect_interface
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Response)() {
  object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_member_array[1].members_ =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, msg, ObjectData)();
  if (!object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_type_support_handle.typesupport_identifier) {
    object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &object_detect_interface__srv__DetectObjects_Response__rosidl_typesupport_introspection_c__DetectObjects_Response_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif

#include "rosidl_runtime_c/service_type_support_struct.h"
// already included above
// #include "object_detect_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__rosidl_typesupport_introspection_c.h"
// already included above
// #include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/service_introspection.h"

// this is intentionally not const to allow initialization later to prevent an initialization race
static rosidl_typesupport_introspection_c__ServiceMembers object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_members = {
  "object_detect_interface__srv",  // service namespace
  "DetectObjects",  // service name
  // these two fields are initialized below on the first access
  NULL,  // request message
  // object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_Request_message_type_support_handle,
  NULL  // response message
  // object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_Response_message_type_support_handle
};

static rosidl_service_type_support_t object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_type_support_handle = {
  0,
  &object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_members,
  get_service_typesupport_handle_function,
};

// Forward declaration of request/response type support functions
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Request)();

const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Response)();

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_object_detect_interface
const rosidl_service_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects)() {
  if (!object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_type_support_handle.typesupport_identifier) {
    object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  rosidl_typesupport_introspection_c__ServiceMembers * service_members =
    (rosidl_typesupport_introspection_c__ServiceMembers *)object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_type_support_handle.data;

  if (!service_members->request_members_) {
    service_members->request_members_ =
      (const rosidl_typesupport_introspection_c__MessageMembers *)
      ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Request)()->data;
  }
  if (!service_members->response_members_) {
    service_members->response_members_ =
      (const rosidl_typesupport_introspection_c__MessageMembers *)
      ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, object_detect_interface, srv, DetectObjects_Response)()->data;
  }

  return &object_detect_interface__srv__detail__detect_objects__rosidl_typesupport_introspection_c__DetectObjects_service_type_support_handle;
}
