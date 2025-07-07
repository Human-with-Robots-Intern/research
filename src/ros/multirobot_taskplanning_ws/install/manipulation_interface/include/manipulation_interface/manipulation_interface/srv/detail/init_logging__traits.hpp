// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from manipulation_interface:srv/InitLogging.idl
// generated code does not contain a copyright notice

#ifndef MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__TRAITS_HPP_
#define MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "manipulation_interface/srv/detail/init_logging__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace manipulation_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const InitLogging_Request & msg,
  std::ostream & out)
{
  out << "{";
  // member: object_id
  {
    out << "object_id: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id, out);
    out << ", ";
  }

  // member: action_id
  {
    out << "action_id: ";
    rosidl_generator_traits::value_to_yaml(msg.action_id, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const InitLogging_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: object_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "object_id: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id, out);
    out << "\n";
  }

  // member: action_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "action_id: ";
    rosidl_generator_traits::value_to_yaml(msg.action_id, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const InitLogging_Request & msg, bool use_flow_style = false)
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

}  // namespace manipulation_interface

namespace rosidl_generator_traits
{

[[deprecated("use manipulation_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const manipulation_interface::srv::InitLogging_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  manipulation_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use manipulation_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const manipulation_interface::srv::InitLogging_Request & msg)
{
  return manipulation_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<manipulation_interface::srv::InitLogging_Request>()
{
  return "manipulation_interface::srv::InitLogging_Request";
}

template<>
inline const char * name<manipulation_interface::srv::InitLogging_Request>()
{
  return "manipulation_interface/srv/InitLogging_Request";
}

template<>
struct has_fixed_size<manipulation_interface::srv::InitLogging_Request>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<manipulation_interface::srv::InitLogging_Request>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<manipulation_interface::srv::InitLogging_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace manipulation_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const InitLogging_Response & msg,
  std::ostream & out)
{
  out << "{";
  // member: success
  {
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const InitLogging_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const InitLogging_Response & msg, bool use_flow_style = false)
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

}  // namespace manipulation_interface

namespace rosidl_generator_traits
{

[[deprecated("use manipulation_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const manipulation_interface::srv::InitLogging_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  manipulation_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use manipulation_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const manipulation_interface::srv::InitLogging_Response & msg)
{
  return manipulation_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<manipulation_interface::srv::InitLogging_Response>()
{
  return "manipulation_interface::srv::InitLogging_Response";
}

template<>
inline const char * name<manipulation_interface::srv::InitLogging_Response>()
{
  return "manipulation_interface/srv/InitLogging_Response";
}

template<>
struct has_fixed_size<manipulation_interface::srv::InitLogging_Response>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<manipulation_interface::srv::InitLogging_Response>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<manipulation_interface::srv::InitLogging_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<manipulation_interface::srv::InitLogging>()
{
  return "manipulation_interface::srv::InitLogging";
}

template<>
inline const char * name<manipulation_interface::srv::InitLogging>()
{
  return "manipulation_interface/srv/InitLogging";
}

template<>
struct has_fixed_size<manipulation_interface::srv::InitLogging>
  : std::integral_constant<
    bool,
    has_fixed_size<manipulation_interface::srv::InitLogging_Request>::value &&
    has_fixed_size<manipulation_interface::srv::InitLogging_Response>::value
  >
{
};

template<>
struct has_bounded_size<manipulation_interface::srv::InitLogging>
  : std::integral_constant<
    bool,
    has_bounded_size<manipulation_interface::srv::InitLogging_Request>::value &&
    has_bounded_size<manipulation_interface::srv::InitLogging_Response>::value
  >
{
};

template<>
struct is_service<manipulation_interface::srv::InitLogging>
  : std::true_type
{
};

template<>
struct is_service_request<manipulation_interface::srv::InitLogging_Request>
  : std::true_type
{
};

template<>
struct is_service_response<manipulation_interface::srv::InitLogging_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__TRAITS_HPP_
