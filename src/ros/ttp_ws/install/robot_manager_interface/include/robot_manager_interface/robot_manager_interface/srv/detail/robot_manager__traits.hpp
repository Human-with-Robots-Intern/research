// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from robot_manager_interface:srv/RobotManager.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__TRAITS_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "robot_manager_interface/srv/detail/robot_manager__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace robot_manager_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const RobotManager_Request & msg,
  std::ostream & out)
{
  out << "{";
  // member: robot_model
  {
    out << "robot_model: ";
    rosidl_generator_traits::value_to_yaml(msg.robot_model, out);
    out << ", ";
  }

  // member: instruction
  {
    out << "instruction: ";
    rosidl_generator_traits::value_to_yaml(msg.instruction, out);
    out << ", ";
  }

  // member: a
  {
    out << "a: ";
    rosidl_generator_traits::value_to_yaml(msg.a, out);
    out << ", ";
  }

  // member: b
  {
    out << "b: ";
    rosidl_generator_traits::value_to_yaml(msg.b, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const RobotManager_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: robot_model
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "robot_model: ";
    rosidl_generator_traits::value_to_yaml(msg.robot_model, out);
    out << "\n";
  }

  // member: instruction
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "instruction: ";
    rosidl_generator_traits::value_to_yaml(msg.instruction, out);
    out << "\n";
  }

  // member: a
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "a: ";
    rosidl_generator_traits::value_to_yaml(msg.a, out);
    out << "\n";
  }

  // member: b
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "b: ";
    rosidl_generator_traits::value_to_yaml(msg.b, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const RobotManager_Request & msg, bool use_flow_style = false)
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

}  // namespace robot_manager_interface

namespace rosidl_generator_traits
{

[[deprecated("use robot_manager_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const robot_manager_interface::srv::RobotManager_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  robot_manager_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robot_manager_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robot_manager_interface::srv::RobotManager_Request & msg)
{
  return robot_manager_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robot_manager_interface::srv::RobotManager_Request>()
{
  return "robot_manager_interface::srv::RobotManager_Request";
}

template<>
inline const char * name<robot_manager_interface::srv::RobotManager_Request>()
{
  return "robot_manager_interface/srv/RobotManager_Request";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::RobotManager_Request>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robot_manager_interface::srv::RobotManager_Request>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robot_manager_interface::srv::RobotManager_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace robot_manager_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const RobotManager_Response & msg,
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
  const RobotManager_Response & msg,
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

inline std::string to_yaml(const RobotManager_Response & msg, bool use_flow_style = false)
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

}  // namespace robot_manager_interface

namespace rosidl_generator_traits
{

[[deprecated("use robot_manager_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const robot_manager_interface::srv::RobotManager_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  robot_manager_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robot_manager_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robot_manager_interface::srv::RobotManager_Response & msg)
{
  return robot_manager_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robot_manager_interface::srv::RobotManager_Response>()
{
  return "robot_manager_interface::srv::RobotManager_Response";
}

template<>
inline const char * name<robot_manager_interface::srv::RobotManager_Response>()
{
  return "robot_manager_interface/srv/RobotManager_Response";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::RobotManager_Response>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robot_manager_interface::srv::RobotManager_Response>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robot_manager_interface::srv::RobotManager_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<robot_manager_interface::srv::RobotManager>()
{
  return "robot_manager_interface::srv::RobotManager";
}

template<>
inline const char * name<robot_manager_interface::srv::RobotManager>()
{
  return "robot_manager_interface/srv/RobotManager";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::RobotManager>
  : std::integral_constant<
    bool,
    has_fixed_size<robot_manager_interface::srv::RobotManager_Request>::value &&
    has_fixed_size<robot_manager_interface::srv::RobotManager_Response>::value
  >
{
};

template<>
struct has_bounded_size<robot_manager_interface::srv::RobotManager>
  : std::integral_constant<
    bool,
    has_bounded_size<robot_manager_interface::srv::RobotManager_Request>::value &&
    has_bounded_size<robot_manager_interface::srv::RobotManager_Response>::value
  >
{
};

template<>
struct is_service<robot_manager_interface::srv::RobotManager>
  : std::true_type
{
};

template<>
struct is_service_request<robot_manager_interface::srv::RobotManager_Request>
  : std::true_type
{
};

template<>
struct is_service_response<robot_manager_interface::srv::RobotManager_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__TRAITS_HPP_
