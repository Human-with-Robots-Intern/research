// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from robotiq_gripper_interface:srv/GetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__TRAITS_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "robotiq_gripper_interface/srv/detail/get_gripper_state_command__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace robotiq_gripper_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const GetGripperStateCommand_Request & msg,
  std::ostream & out)
{
  (void)msg;
  out << "null";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const GetGripperStateCommand_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  (void)msg;
  (void)indentation;
  out << "null\n";
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const GetGripperStateCommand_Request & msg, bool use_flow_style = false)
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

}  // namespace robotiq_gripper_interface

namespace rosidl_generator_traits
{

[[deprecated("use robotiq_gripper_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const robotiq_gripper_interface::srv::GetGripperStateCommand_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  robotiq_gripper_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robotiq_gripper_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robotiq_gripper_interface::srv::GetGripperStateCommand_Request & msg)
{
  return robotiq_gripper_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>()
{
  return "robotiq_gripper_interface::srv::GetGripperStateCommand_Request";
}

template<>
inline const char * name<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>()
{
  return "robotiq_gripper_interface/srv/GetGripperStateCommand_Request";
}

template<>
struct has_fixed_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace robotiq_gripper_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const GetGripperStateCommand_Response & msg,
  std::ostream & out)
{
  out << "{";
  // member: position
  {
    out << "position: ";
    rosidl_generator_traits::value_to_yaml(msg.position, out);
    out << ", ";
  }

  // member: speed
  {
    out << "speed: ";
    rosidl_generator_traits::value_to_yaml(msg.speed, out);
    out << ", ";
  }

  // member: force
  {
    out << "force: ";
    rosidl_generator_traits::value_to_yaml(msg.force, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const GetGripperStateCommand_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: position
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "position: ";
    rosidl_generator_traits::value_to_yaml(msg.position, out);
    out << "\n";
  }

  // member: speed
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "speed: ";
    rosidl_generator_traits::value_to_yaml(msg.speed, out);
    out << "\n";
  }

  // member: force
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "force: ";
    rosidl_generator_traits::value_to_yaml(msg.force, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const GetGripperStateCommand_Response & msg, bool use_flow_style = false)
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

}  // namespace robotiq_gripper_interface

namespace rosidl_generator_traits
{

[[deprecated("use robotiq_gripper_interface::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const robotiq_gripper_interface::srv::GetGripperStateCommand_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  robotiq_gripper_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robotiq_gripper_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robotiq_gripper_interface::srv::GetGripperStateCommand_Response & msg)
{
  return robotiq_gripper_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>()
{
  return "robotiq_gripper_interface::srv::GetGripperStateCommand_Response";
}

template<>
inline const char * name<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>()
{
  return "robotiq_gripper_interface/srv/GetGripperStateCommand_Response";
}

template<>
struct has_fixed_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<robotiq_gripper_interface::srv::GetGripperStateCommand>()
{
  return "robotiq_gripper_interface::srv::GetGripperStateCommand";
}

template<>
inline const char * name<robotiq_gripper_interface::srv::GetGripperStateCommand>()
{
  return "robotiq_gripper_interface/srv/GetGripperStateCommand";
}

template<>
struct has_fixed_size<robotiq_gripper_interface::srv::GetGripperStateCommand>
  : std::integral_constant<
    bool,
    has_fixed_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>::value &&
    has_fixed_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>::value
  >
{
};

template<>
struct has_bounded_size<robotiq_gripper_interface::srv::GetGripperStateCommand>
  : std::integral_constant<
    bool,
    has_bounded_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>::value &&
    has_bounded_size<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>::value
  >
{
};

template<>
struct is_service<robotiq_gripper_interface::srv::GetGripperStateCommand>
  : std::true_type
{
};

template<>
struct is_service_request<robotiq_gripper_interface::srv::GetGripperStateCommand_Request>
  : std::true_type
{
};

template<>
struct is_service_response<robotiq_gripper_interface::srv::GetGripperStateCommand_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__TRAITS_HPP_
