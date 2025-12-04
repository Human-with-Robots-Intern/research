// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from franka_msgs:srv/ErrorRecovery.idl
// generated code does not contain a copyright notice

#ifndef FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__TRAITS_HPP_
#define FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "franka_msgs/srv/detail/error_recovery__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace franka_msgs
{

namespace srv
{

inline void to_flow_style_yaml(
  const ErrorRecovery_Request & msg,
  std::ostream & out)
{
  (void)msg;
  out << "null";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const ErrorRecovery_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  (void)msg;
  (void)indentation;
  out << "null\n";
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const ErrorRecovery_Request & msg, bool use_flow_style = false)
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

}  // namespace franka_msgs

namespace rosidl_generator_traits
{

[[deprecated("use franka_msgs::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const franka_msgs::srv::ErrorRecovery_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  franka_msgs::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use franka_msgs::srv::to_yaml() instead")]]
inline std::string to_yaml(const franka_msgs::srv::ErrorRecovery_Request & msg)
{
  return franka_msgs::srv::to_yaml(msg);
}

template<>
inline const char * data_type<franka_msgs::srv::ErrorRecovery_Request>()
{
  return "franka_msgs::srv::ErrorRecovery_Request";
}

template<>
inline const char * name<franka_msgs::srv::ErrorRecovery_Request>()
{
  return "franka_msgs/srv/ErrorRecovery_Request";
}

template<>
struct has_fixed_size<franka_msgs::srv::ErrorRecovery_Request>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<franka_msgs::srv::ErrorRecovery_Request>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<franka_msgs::srv::ErrorRecovery_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace franka_msgs
{

namespace srv
{

inline void to_flow_style_yaml(
  const ErrorRecovery_Response & msg,
  std::ostream & out)
{
  out << "{";
  // member: success
  {
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << ", ";
  }

  // member: error
  {
    out << "error: ";
    rosidl_generator_traits::value_to_yaml(msg.error, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const ErrorRecovery_Response & msg,
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

  // member: error
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "error: ";
    rosidl_generator_traits::value_to_yaml(msg.error, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const ErrorRecovery_Response & msg, bool use_flow_style = false)
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

}  // namespace franka_msgs

namespace rosidl_generator_traits
{

[[deprecated("use franka_msgs::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const franka_msgs::srv::ErrorRecovery_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  franka_msgs::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use franka_msgs::srv::to_yaml() instead")]]
inline std::string to_yaml(const franka_msgs::srv::ErrorRecovery_Response & msg)
{
  return franka_msgs::srv::to_yaml(msg);
}

template<>
inline const char * data_type<franka_msgs::srv::ErrorRecovery_Response>()
{
  return "franka_msgs::srv::ErrorRecovery_Response";
}

template<>
inline const char * name<franka_msgs::srv::ErrorRecovery_Response>()
{
  return "franka_msgs/srv/ErrorRecovery_Response";
}

template<>
struct has_fixed_size<franka_msgs::srv::ErrorRecovery_Response>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<franka_msgs::srv::ErrorRecovery_Response>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<franka_msgs::srv::ErrorRecovery_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<franka_msgs::srv::ErrorRecovery>()
{
  return "franka_msgs::srv::ErrorRecovery";
}

template<>
inline const char * name<franka_msgs::srv::ErrorRecovery>()
{
  return "franka_msgs/srv/ErrorRecovery";
}

template<>
struct has_fixed_size<franka_msgs::srv::ErrorRecovery>
  : std::integral_constant<
    bool,
    has_fixed_size<franka_msgs::srv::ErrorRecovery_Request>::value &&
    has_fixed_size<franka_msgs::srv::ErrorRecovery_Response>::value
  >
{
};

template<>
struct has_bounded_size<franka_msgs::srv::ErrorRecovery>
  : std::integral_constant<
    bool,
    has_bounded_size<franka_msgs::srv::ErrorRecovery_Request>::value &&
    has_bounded_size<franka_msgs::srv::ErrorRecovery_Response>::value
  >
{
};

template<>
struct is_service<franka_msgs::srv::ErrorRecovery>
  : std::true_type
{
};

template<>
struct is_service_request<franka_msgs::srv::ErrorRecovery_Request>
  : std::true_type
{
};

template<>
struct is_service_response<franka_msgs::srv::ErrorRecovery_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__TRAITS_HPP_
