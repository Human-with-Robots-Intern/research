// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__TRAITS_HPP_
#define OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "object_detect_interface/srv/detail/detect_objects__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace object_detect_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const DetectObjects_Request & msg,
  std::ostream & out)
{
  (void)msg;
  out << "null";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const DetectObjects_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  (void)msg;
  (void)indentation;
  out << "null\n";
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const DetectObjects_Request & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace srv

}  // namespace object_detect_interface

namespace rosidl_generator_traits
{

[[deprecated("use object_detect_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const object_detect_interface::srv::DetectObjects_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  object_detect_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use object_detect_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const object_detect_interface::srv::DetectObjects_Request & msg)
{
  return object_detect_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<object_detect_interface::srv::DetectObjects_Request>()
{
  return "object_detect_interface::srv::DetectObjects_Request";
}

template<>
inline const char * name<object_detect_interface::srv::DetectObjects_Request>()
{
  return "object_detect_interface/srv/DetectObjects_Request";
}

template<>
struct has_fixed_size<object_detect_interface::srv::DetectObjects_Request>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<object_detect_interface::srv::DetectObjects_Request>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<object_detect_interface::srv::DetectObjects_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

// Include directives for member types
// Member 'object_list'
#include "object_detect_interface/msg/detail/object_data__traits.hpp"

namespace object_detect_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const DetectObjects_Response & msg,
  std::ostream & out)
{
  out << "{";
  // member: entity_num
  {
    out << "entity_num: ";
    rosidl_generator_traits::value_to_yaml(msg.entity_num, out);
    out << ", ";
  }

  // member: object_list
  {
    if (msg.object_list.size() == 0) {
      out << "object_list: []";
    } else {
      out << "object_list: [";
      size_t pending_items = msg.object_list.size();
      for (auto item : msg.object_list) {
        to_flow_style_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const DetectObjects_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: entity_num
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "entity_num: ";
    rosidl_generator_traits::value_to_yaml(msg.entity_num, out);
    out << "\n";
  }

  // member: object_list
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.object_list.size() == 0) {
      out << "object_list: []\n";
    } else {
      out << "object_list:\n";
      for (auto item : msg.object_list) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "-\n";
        to_block_style_yaml(item, out, indentation + 2);
      }
    }
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const DetectObjects_Response & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace srv

}  // namespace object_detect_interface

namespace rosidl_generator_traits
{

[[deprecated("use object_detect_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const object_detect_interface::srv::DetectObjects_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  object_detect_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use object_detect_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const object_detect_interface::srv::DetectObjects_Response & msg)
{
  return object_detect_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<object_detect_interface::srv::DetectObjects_Response>()
{
  return "object_detect_interface::srv::DetectObjects_Response";
}

template<>
inline const char * name<object_detect_interface::srv::DetectObjects_Response>()
{
  return "object_detect_interface/srv/DetectObjects_Response";
}

template<>
struct has_fixed_size<object_detect_interface::srv::DetectObjects_Response>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<object_detect_interface::srv::DetectObjects_Response>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<object_detect_interface::srv::DetectObjects_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<object_detect_interface::srv::DetectObjects>()
{
  return "object_detect_interface::srv::DetectObjects";
}

template<>
inline const char * name<object_detect_interface::srv::DetectObjects>()
{
  return "object_detect_interface/srv/DetectObjects";
}

template<>
struct has_fixed_size<object_detect_interface::srv::DetectObjects>
  : std::integral_constant<
    bool,
    has_fixed_size<object_detect_interface::srv::DetectObjects_Request>::value &&
    has_fixed_size<object_detect_interface::srv::DetectObjects_Response>::value
  >
{
};

template<>
struct has_bounded_size<object_detect_interface::srv::DetectObjects>
  : std::integral_constant<
    bool,
    has_bounded_size<object_detect_interface::srv::DetectObjects_Request>::value &&
    has_bounded_size<object_detect_interface::srv::DetectObjects_Response>::value
  >
{
};

template<>
struct is_service<object_detect_interface::srv::DetectObjects>
  : std::true_type
{
};

template<>
struct is_service_request<object_detect_interface::srv::DetectObjects_Request>
  : std::true_type
{
};

template<>
struct is_service_response<object_detect_interface::srv::DetectObjects_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__TRAITS_HPP_
