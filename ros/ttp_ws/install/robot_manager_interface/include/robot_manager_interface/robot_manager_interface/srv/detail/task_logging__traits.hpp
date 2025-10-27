// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__TRAITS_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "robot_manager_interface/srv/detail/task_logging__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace robot_manager_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const TaskLogging_Request & msg,
  std::ostream & out)
{
  out << "{";
  // member: object_id_a
  {
    out << "object_id_a: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id_a, out);
    out << ", ";
  }

  // member: object_id_b
  {
    out << "object_id_b: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id_b, out);
    out << ", ";
  }

  // member: instruction
  {
    out << "instruction: ";
    rosidl_generator_traits::value_to_yaml(msg.instruction, out);
    out << ", ";
  }

  // member: sequence_id
  {
    out << "sequence_id: ";
    rosidl_generator_traits::value_to_yaml(msg.sequence_id, out);
    out << ", ";
  }

  // member: sub_action
  {
    out << "sub_action: ";
    rosidl_generator_traits::value_to_yaml(msg.sub_action, out);
    out << ", ";
  }

  // member: relativity
  {
    out << "relativity: ";
    rosidl_generator_traits::value_to_yaml(msg.relativity, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const TaskLogging_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: object_id_a
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "object_id_a: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id_a, out);
    out << "\n";
  }

  // member: object_id_b
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "object_id_b: ";
    rosidl_generator_traits::value_to_yaml(msg.object_id_b, out);
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

  // member: sequence_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "sequence_id: ";
    rosidl_generator_traits::value_to_yaml(msg.sequence_id, out);
    out << "\n";
  }

  // member: sub_action
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "sub_action: ";
    rosidl_generator_traits::value_to_yaml(msg.sub_action, out);
    out << "\n";
  }

  // member: relativity
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "relativity: ";
    rosidl_generator_traits::value_to_yaml(msg.relativity, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const TaskLogging_Request & msg, bool use_flow_style = false)
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
  const robot_manager_interface::srv::TaskLogging_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  robot_manager_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robot_manager_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robot_manager_interface::srv::TaskLogging_Request & msg)
{
  return robot_manager_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robot_manager_interface::srv::TaskLogging_Request>()
{
  return "robot_manager_interface::srv::TaskLogging_Request";
}

template<>
inline const char * name<robot_manager_interface::srv::TaskLogging_Request>()
{
  return "robot_manager_interface/srv/TaskLogging_Request";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::TaskLogging_Request>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<robot_manager_interface::srv::TaskLogging_Request>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<robot_manager_interface::srv::TaskLogging_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace robot_manager_interface
{

namespace srv
{

inline void to_flow_style_yaml(
  const TaskLogging_Response & msg,
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
  const TaskLogging_Response & msg,
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

inline std::string to_yaml(const TaskLogging_Response & msg, bool use_flow_style = false)
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
  const robot_manager_interface::srv::TaskLogging_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  robot_manager_interface::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robot_manager_interface::srv::to_yaml() instead")]]
inline std::string to_yaml(const robot_manager_interface::srv::TaskLogging_Response & msg)
{
  return robot_manager_interface::srv::to_yaml(msg);
}

template<>
inline const char * data_type<robot_manager_interface::srv::TaskLogging_Response>()
{
  return "robot_manager_interface::srv::TaskLogging_Response";
}

template<>
inline const char * name<robot_manager_interface::srv::TaskLogging_Response>()
{
  return "robot_manager_interface/srv/TaskLogging_Response";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::TaskLogging_Response>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robot_manager_interface::srv::TaskLogging_Response>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robot_manager_interface::srv::TaskLogging_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<robot_manager_interface::srv::TaskLogging>()
{
  return "robot_manager_interface::srv::TaskLogging";
}

template<>
inline const char * name<robot_manager_interface::srv::TaskLogging>()
{
  return "robot_manager_interface/srv/TaskLogging";
}

template<>
struct has_fixed_size<robot_manager_interface::srv::TaskLogging>
  : std::integral_constant<
    bool,
    has_fixed_size<robot_manager_interface::srv::TaskLogging_Request>::value &&
    has_fixed_size<robot_manager_interface::srv::TaskLogging_Response>::value
  >
{
};

template<>
struct has_bounded_size<robot_manager_interface::srv::TaskLogging>
  : std::integral_constant<
    bool,
    has_bounded_size<robot_manager_interface::srv::TaskLogging_Request>::value &&
    has_bounded_size<robot_manager_interface::srv::TaskLogging_Response>::value
  >
{
};

template<>
struct is_service<robot_manager_interface::srv::TaskLogging>
  : std::true_type
{
};

template<>
struct is_service_request<robot_manager_interface::srv::TaskLogging_Request>
  : std::true_type
{
};

template<>
struct is_service_response<robot_manager_interface::srv::TaskLogging_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__TRAITS_HPP_
