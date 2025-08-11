// generated from rosidl_typesupport_introspection_cpp/resource/idl__type_support.cpp.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#include "array"
#include "cstddef"
#include "string"
#include "vector"
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_typesupport_cpp/message_type_support.hpp"
#include "rosidl_typesupport_interface/macros.h"
#include "object_detect_interface/srv/detail/detect_objects__struct.hpp"
#include "rosidl_typesupport_introspection_cpp/field_types.hpp"
#include "rosidl_typesupport_introspection_cpp/identifier.hpp"
#include "rosidl_typesupport_introspection_cpp/message_introspection.hpp"
#include "rosidl_typesupport_introspection_cpp/message_type_support_decl.hpp"
#include "rosidl_typesupport_introspection_cpp/visibility_control.h"

namespace object_detect_interface
{

namespace srv
{

namespace rosidl_typesupport_introspection_cpp
{

void DetectObjects_Request_init_function(
  void * message_memory, rosidl_runtime_cpp::MessageInitialization _init)
{
  new (message_memory) object_detect_interface::srv::DetectObjects_Request(_init);
}

void DetectObjects_Request_fini_function(void * message_memory)
{
  auto typed_message = static_cast<object_detect_interface::srv::DetectObjects_Request *>(message_memory);
  typed_message->~DetectObjects_Request();
}

static const ::rosidl_typesupport_introspection_cpp::MessageMember DetectObjects_Request_message_member_array[1] = {
  {
    "structure_needs_at_least_one_member",  // name
    ::rosidl_typesupport_introspection_cpp::ROS_TYPE_UINT8,  // type
    0,  // upper bound of string
    nullptr,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface::srv::DetectObjects_Request, structure_needs_at_least_one_member),  // bytes offset in struct
    nullptr,  // default value
    nullptr,  // size() function pointer
    nullptr,  // get_const(index) function pointer
    nullptr,  // get(index) function pointer
    nullptr,  // fetch(index, &value) function pointer
    nullptr,  // assign(index, value) function pointer
    nullptr  // resize(index) function pointer
  }
};

static const ::rosidl_typesupport_introspection_cpp::MessageMembers DetectObjects_Request_message_members = {
  "object_detect_interface::srv",  // message namespace
  "DetectObjects_Request",  // message name
  1,  // number of fields
  sizeof(object_detect_interface::srv::DetectObjects_Request),
  DetectObjects_Request_message_member_array,  // message members
  DetectObjects_Request_init_function,  // function to initialize message memory (memory has to be allocated)
  DetectObjects_Request_fini_function  // function to terminate message instance (will not free memory)
};

static const rosidl_message_type_support_t DetectObjects_Request_message_type_support_handle = {
  ::rosidl_typesupport_introspection_cpp::typesupport_identifier,
  &DetectObjects_Request_message_members,
  get_message_typesupport_handle_function,
};

}  // namespace rosidl_typesupport_introspection_cpp

}  // namespace srv

}  // namespace object_detect_interface


namespace rosidl_typesupport_introspection_cpp
{

template<>
ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
get_message_type_support_handle<object_detect_interface::srv::DetectObjects_Request>()
{
  return &::object_detect_interface::srv::rosidl_typesupport_introspection_cpp::DetectObjects_Request_message_type_support_handle;
}

}  // namespace rosidl_typesupport_introspection_cpp

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_cpp, object_detect_interface, srv, DetectObjects_Request)() {
  return &::object_detect_interface::srv::rosidl_typesupport_introspection_cpp::DetectObjects_Request_message_type_support_handle;
}

#ifdef __cplusplus
}
#endif

// already included above
// #include "array"
// already included above
// #include "cstddef"
// already included above
// #include "string"
// already included above
// #include "vector"
// already included above
// #include "rosidl_runtime_c/message_type_support_struct.h"
// already included above
// #include "rosidl_typesupport_cpp/message_type_support.hpp"
// already included above
// #include "rosidl_typesupport_interface/macros.h"
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__struct.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/field_types.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/identifier.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/message_introspection.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/message_type_support_decl.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/visibility_control.h"

namespace object_detect_interface
{

namespace srv
{

namespace rosidl_typesupport_introspection_cpp
{

void DetectObjects_Response_init_function(
  void * message_memory, rosidl_runtime_cpp::MessageInitialization _init)
{
  new (message_memory) object_detect_interface::srv::DetectObjects_Response(_init);
}

void DetectObjects_Response_fini_function(void * message_memory)
{
  auto typed_message = static_cast<object_detect_interface::srv::DetectObjects_Response *>(message_memory);
  typed_message->~DetectObjects_Response();
}

size_t size_function__DetectObjects_Response__object_list(const void * untyped_member)
{
  const auto * member = reinterpret_cast<const std::vector<object_detect_interface::msg::ObjectData> *>(untyped_member);
  return member->size();
}

const void * get_const_function__DetectObjects_Response__object_list(const void * untyped_member, size_t index)
{
  const auto & member =
    *reinterpret_cast<const std::vector<object_detect_interface::msg::ObjectData> *>(untyped_member);
  return &member[index];
}

void * get_function__DetectObjects_Response__object_list(void * untyped_member, size_t index)
{
  auto & member =
    *reinterpret_cast<std::vector<object_detect_interface::msg::ObjectData> *>(untyped_member);
  return &member[index];
}

void fetch_function__DetectObjects_Response__object_list(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const auto & item = *reinterpret_cast<const object_detect_interface::msg::ObjectData *>(
    get_const_function__DetectObjects_Response__object_list(untyped_member, index));
  auto & value = *reinterpret_cast<object_detect_interface::msg::ObjectData *>(untyped_value);
  value = item;
}

void assign_function__DetectObjects_Response__object_list(
  void * untyped_member, size_t index, const void * untyped_value)
{
  auto & item = *reinterpret_cast<object_detect_interface::msg::ObjectData *>(
    get_function__DetectObjects_Response__object_list(untyped_member, index));
  const auto & value = *reinterpret_cast<const object_detect_interface::msg::ObjectData *>(untyped_value);
  item = value;
}

void resize_function__DetectObjects_Response__object_list(void * untyped_member, size_t size)
{
  auto * member =
    reinterpret_cast<std::vector<object_detect_interface::msg::ObjectData> *>(untyped_member);
  member->resize(size);
}

static const ::rosidl_typesupport_introspection_cpp::MessageMember DetectObjects_Response_message_member_array[2] = {
  {
    "entity_num",  // name
    ::rosidl_typesupport_introspection_cpp::ROS_TYPE_INT16,  // type
    0,  // upper bound of string
    nullptr,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface::srv::DetectObjects_Response, entity_num),  // bytes offset in struct
    nullptr,  // default value
    nullptr,  // size() function pointer
    nullptr,  // get_const(index) function pointer
    nullptr,  // get(index) function pointer
    nullptr,  // fetch(index, &value) function pointer
    nullptr,  // assign(index, value) function pointer
    nullptr  // resize(index) function pointer
  },
  {
    "object_list",  // name
    ::rosidl_typesupport_introspection_cpp::ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    ::rosidl_typesupport_introspection_cpp::get_message_type_support_handle<object_detect_interface::msg::ObjectData>(),  // members of sub message
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(object_detect_interface::srv::DetectObjects_Response, object_list),  // bytes offset in struct
    nullptr,  // default value
    size_function__DetectObjects_Response__object_list,  // size() function pointer
    get_const_function__DetectObjects_Response__object_list,  // get_const(index) function pointer
    get_function__DetectObjects_Response__object_list,  // get(index) function pointer
    fetch_function__DetectObjects_Response__object_list,  // fetch(index, &value) function pointer
    assign_function__DetectObjects_Response__object_list,  // assign(index, value) function pointer
    resize_function__DetectObjects_Response__object_list  // resize(index) function pointer
  }
};

static const ::rosidl_typesupport_introspection_cpp::MessageMembers DetectObjects_Response_message_members = {
  "object_detect_interface::srv",  // message namespace
  "DetectObjects_Response",  // message name
  2,  // number of fields
  sizeof(object_detect_interface::srv::DetectObjects_Response),
  DetectObjects_Response_message_member_array,  // message members
  DetectObjects_Response_init_function,  // function to initialize message memory (memory has to be allocated)
  DetectObjects_Response_fini_function  // function to terminate message instance (will not free memory)
};

static const rosidl_message_type_support_t DetectObjects_Response_message_type_support_handle = {
  ::rosidl_typesupport_introspection_cpp::typesupport_identifier,
  &DetectObjects_Response_message_members,
  get_message_typesupport_handle_function,
};

}  // namespace rosidl_typesupport_introspection_cpp

}  // namespace srv

}  // namespace object_detect_interface


namespace rosidl_typesupport_introspection_cpp
{

template<>
ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
get_message_type_support_handle<object_detect_interface::srv::DetectObjects_Response>()
{
  return &::object_detect_interface::srv::rosidl_typesupport_introspection_cpp::DetectObjects_Response_message_type_support_handle;
}

}  // namespace rosidl_typesupport_introspection_cpp

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_cpp, object_detect_interface, srv, DetectObjects_Response)() {
  return &::object_detect_interface::srv::rosidl_typesupport_introspection_cpp::DetectObjects_Response_message_type_support_handle;
}

#ifdef __cplusplus
}
#endif

#include "rosidl_runtime_c/service_type_support_struct.h"
// already included above
// #include "rosidl_typesupport_cpp/message_type_support.hpp"
#include "rosidl_typesupport_cpp/service_type_support.hpp"
// already included above
// #include "rosidl_typesupport_interface/macros.h"
// already included above
// #include "rosidl_typesupport_introspection_cpp/visibility_control.h"
// already included above
// #include "object_detect_interface/srv/detail/detect_objects__struct.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/identifier.hpp"
// already included above
// #include "rosidl_typesupport_introspection_cpp/message_type_support_decl.hpp"
#include "rosidl_typesupport_introspection_cpp/service_introspection.hpp"
#include "rosidl_typesupport_introspection_cpp/service_type_support_decl.hpp"

namespace object_detect_interface
{

namespace srv
{

namespace rosidl_typesupport_introspection_cpp
{

// this is intentionally not const to allow initialization later to prevent an initialization race
static ::rosidl_typesupport_introspection_cpp::ServiceMembers DetectObjects_service_members = {
  "object_detect_interface::srv",  // service namespace
  "DetectObjects",  // service name
  // these two fields are initialized below on the first access
  // see get_service_type_support_handle<object_detect_interface::srv::DetectObjects>()
  nullptr,  // request message
  nullptr  // response message
};

static const rosidl_service_type_support_t DetectObjects_service_type_support_handle = {
  ::rosidl_typesupport_introspection_cpp::typesupport_identifier,
  &DetectObjects_service_members,
  get_service_typesupport_handle_function,
};

}  // namespace rosidl_typesupport_introspection_cpp

}  // namespace srv

}  // namespace object_detect_interface


namespace rosidl_typesupport_introspection_cpp
{

template<>
ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_service_type_support_t *
get_service_type_support_handle<object_detect_interface::srv::DetectObjects>()
{
  // get a handle to the value to be returned
  auto service_type_support =
    &::object_detect_interface::srv::rosidl_typesupport_introspection_cpp::DetectObjects_service_type_support_handle;
  // get a non-const and properly typed version of the data void *
  auto service_members = const_cast<::rosidl_typesupport_introspection_cpp::ServiceMembers *>(
    static_cast<const ::rosidl_typesupport_introspection_cpp::ServiceMembers *>(
      service_type_support->data));
  // make sure that both the request_members_ and the response_members_ are initialized
  // if they are not, initialize them
  if (
    service_members->request_members_ == nullptr ||
    service_members->response_members_ == nullptr)
  {
    // initialize the request_members_ with the static function from the external library
    service_members->request_members_ = static_cast<
      const ::rosidl_typesupport_introspection_cpp::MessageMembers *
      >(
      ::rosidl_typesupport_introspection_cpp::get_message_type_support_handle<
        ::object_detect_interface::srv::DetectObjects_Request
      >()->data
      );
    // initialize the response_members_ with the static function from the external library
    service_members->response_members_ = static_cast<
      const ::rosidl_typesupport_introspection_cpp::MessageMembers *
      >(
      ::rosidl_typesupport_introspection_cpp::get_message_type_support_handle<
        ::object_detect_interface::srv::DetectObjects_Response
      >()->data
      );
  }
  // finally return the properly initialized service_type_support handle
  return service_type_support;
}

}  // namespace rosidl_typesupport_introspection_cpp

#ifdef __cplusplus
extern "C"
{
#endif

ROSIDL_TYPESUPPORT_INTROSPECTION_CPP_PUBLIC
const rosidl_service_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__SERVICE_SYMBOL_NAME(rosidl_typesupport_introspection_cpp, object_detect_interface, srv, DetectObjects)() {
  return ::rosidl_typesupport_introspection_cpp::get_service_type_support_handle<object_detect_interface::srv::DetectObjects>();
}

#ifdef __cplusplus
}
#endif
