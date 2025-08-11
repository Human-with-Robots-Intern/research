// generated from rosidl_typesupport_introspection_c/resource/idl__type_support.c.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice

#include <stddef.h>
#include "robot_manager_interface/srv/detail/task_logging__rosidl_typesupport_introspection_c.h"
#include "robot_manager_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "robot_manager_interface/srv/detail/task_logging__functions.h"
#include "robot_manager_interface/srv/detail/task_logging__struct.h"


// Include directives for member types
// Member `sub_action`
#include "rosidl_runtime_c/string_functions.h"

#ifdef __cplusplus
extern "C"
{
#endif

void robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  robot_manager_interface__srv__TaskLogging_Request__init(message_memory);
}

void robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_fini_function(void * message_memory)
{
  robot_manager_interface__srv__TaskLogging_Request__fini(message_memory);
}

static rosidl_typesupport_introspection_c__MessageMember robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_member_array[6] = {
  {
    "object_id_a",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, object_id_a),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "object_id_b",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, object_id_b),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "instruction",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, instruction),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "sequence_id",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, sequence_id),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "sub_action",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_STRING,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, sub_action),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "relativity",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_BOOLEAN,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Request, relativity),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_members = {
  "robot_manager_interface__srv",  // message namespace
  "TaskLogging_Request",  // message name
  6,  // number of fields
  sizeof(robot_manager_interface__srv__TaskLogging_Request),
  robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_member_array,  // message members
  robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_init_function,  // function to initialize message memory (memory has to be allocated)
  robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_type_support_handle = {
  0,
  &robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robot_manager_interface
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Request)() {
  if (!robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_type_support_handle.typesupport_identifier) {
    robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &robot_manager_interface__srv__TaskLogging_Request__rosidl_typesupport_introspection_c__TaskLogging_Request_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif

// already included above
// #include <stddef.h>
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__rosidl_typesupport_introspection_c.h"
// already included above
// #include "robot_manager_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
// already included above
// #include "rosidl_typesupport_introspection_c/field_types.h"
// already included above
// #include "rosidl_typesupport_introspection_c/identifier.h"
// already included above
// #include "rosidl_typesupport_introspection_c/message_introspection.h"
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__functions.h"
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__struct.h"


#ifdef __cplusplus
extern "C"
{
#endif

void robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  robot_manager_interface__srv__TaskLogging_Response__init(message_memory);
}

void robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_fini_function(void * message_memory)
{
  robot_manager_interface__srv__TaskLogging_Response__fini(message_memory);
}

static rosidl_typesupport_introspection_c__MessageMember robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_member_array[1] = {
  {
    "success",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_BOOLEAN,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(robot_manager_interface__srv__TaskLogging_Response, success),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_members = {
  "robot_manager_interface__srv",  // message namespace
  "TaskLogging_Response",  // message name
  1,  // number of fields
  sizeof(robot_manager_interface__srv__TaskLogging_Response),
  robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_member_array,  // message members
  robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_init_function,  // function to initialize message memory (memory has to be allocated)
  robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_type_support_handle = {
  0,
  &robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robot_manager_interface
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Response)() {
  if (!robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_type_support_handle.typesupport_identifier) {
    robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &robot_manager_interface__srv__TaskLogging_Response__rosidl_typesupport_introspection_c__TaskLogging_Response_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif

#include "rosidl_runtime_c/service_type_support_struct.h"
// already included above
// #include "robot_manager_interface/msg/rosidl_typesupport_introspection_c__visibility_control.h"
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__rosidl_typesupport_introspection_c.h"
// already included above
// #include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/service_introspection.h"

// this is intentionally not const to allow initialization later to prevent an initialization race
static rosidl_typesupport_introspection_c__ServiceMembers robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_members = {
  "robot_manager_interface__srv",  // service namespace
  "TaskLogging",  // service name
  // these two fields are initialized below on the first access
  NULL,  // request message
  // robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_Request_message_type_support_handle,
  NULL  // response message
  // robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_Response_message_type_support_handle
};

static rosidl_service_type_support_t robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_type_support_handle = {
  0,
  &robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_members,
  get_service_typesupport_handle_function,
};

// Forward declaration of request/response type support functions
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Request)();

const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Response)();

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robot_manager_interface
const rosidl_service_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging)() {
  if (!robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_type_support_handle.typesupport_identifier) {
    robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  rosidl_typesupport_introspection_c__ServiceMembers * service_members =
    (rosidl_typesupport_introspection_c__ServiceMembers *)robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_type_support_handle.data;

  if (!service_members->request_members_) {
    service_members->request_members_ =
      (const rosidl_typesupport_introspection_c__MessageMembers *)
      ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Request)()->data;
  }
  if (!service_members->response_members_) {
    service_members->response_members_ =
      (const rosidl_typesupport_introspection_c__MessageMembers *)
      ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, robot_manager_interface, srv, TaskLogging_Response)()->data;
  }

  return &robot_manager_interface__srv__detail__task_logging__rosidl_typesupport_introspection_c__TaskLogging_service_type_support_handle;
}
