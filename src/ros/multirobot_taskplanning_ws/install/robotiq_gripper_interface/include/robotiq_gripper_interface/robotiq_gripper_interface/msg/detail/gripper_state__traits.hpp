// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__TRAITS_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "robotiq_gripper_interface/msg/detail/gripper_state__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace robotiq_gripper_interface
{

namespace msg
{

inline void to_flow_style_yaml(
  const GripperState & msg,
  std::ostream & out)
{
  out << "{";
  // member: g_act
  {
    out << "g_act: ";
    rosidl_generator_traits::value_to_yaml(msg.g_act, out);
    out << ", ";
  }

  // member: g_gto
  {
    out << "g_gto: ";
    rosidl_generator_traits::value_to_yaml(msg.g_gto, out);
    out << ", ";
  }

  // member: g_sta
  {
    out << "g_sta: ";
    rosidl_generator_traits::value_to_yaml(msg.g_sta, out);
    out << ", ";
  }

  // member: g_obj
  {
    out << "g_obj: ";
    rosidl_generator_traits::value_to_yaml(msg.g_obj, out);
    out << ", ";
  }

  // member: g_flt
  {
    out << "g_flt: ";
    rosidl_generator_traits::value_to_yaml(msg.g_flt, out);
    out << ", ";
  }

  // member: g_pr
  {
    out << "g_pr: ";
    rosidl_generator_traits::value_to_yaml(msg.g_pr, out);
    out << ", ";
  }

  // member: g_po
  {
    out << "g_po: ";
    rosidl_generator_traits::value_to_yaml(msg.g_po, out);
    out << ", ";
  }

  // member: g_cu
  {
    out << "g_cu: ";
    rosidl_generator_traits::value_to_yaml(msg.g_cu, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const GripperState & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: g_act
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_act: ";
    rosidl_generator_traits::value_to_yaml(msg.g_act, out);
    out << "\n";
  }

  // member: g_gto
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_gto: ";
    rosidl_generator_traits::value_to_yaml(msg.g_gto, out);
    out << "\n";
  }

  // member: g_sta
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_sta: ";
    rosidl_generator_traits::value_to_yaml(msg.g_sta, out);
    out << "\n";
  }

  // member: g_obj
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_obj: ";
    rosidl_generator_traits::value_to_yaml(msg.g_obj, out);
    out << "\n";
  }

  // member: g_flt
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_flt: ";
    rosidl_generator_traits::value_to_yaml(msg.g_flt, out);
    out << "\n";
  }

  // member: g_pr
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_pr: ";
    rosidl_generator_traits::value_to_yaml(msg.g_pr, out);
    out << "\n";
  }

  // member: g_po
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_po: ";
    rosidl_generator_traits::value_to_yaml(msg.g_po, out);
    out << "\n";
  }

  // member: g_cu
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "g_cu: ";
    rosidl_generator_traits::value_to_yaml(msg.g_cu, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const GripperState & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace msg

}  // namespace robotiq_gripper_interface

namespace rosidl_generator_traits
{

[[deprecated("use robotiq_gripper_interface::msg::to_block_style_yaml() instead")]]
inline void to_yaml(
  const robotiq_gripper_interface::msg::GripperState & msg,
  std::ostream & out, size_t indentation = 0)
{
  robotiq_gripper_interface::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use robotiq_gripper_interface::msg::to_yaml() instead")]]
inline std::string to_yaml(const robotiq_gripper_interface::msg::GripperState & msg)
{
  return robotiq_gripper_interface::msg::to_yaml(msg);
}

template<>
inline const char * data_type<robotiq_gripper_interface::msg::GripperState>()
{
  return "robotiq_gripper_interface::msg::GripperState";
}

template<>
inline const char * name<robotiq_gripper_interface::msg::GripperState>()
{
  return "robotiq_gripper_interface/msg/GripperState";
}

template<>
struct has_fixed_size<robotiq_gripper_interface::msg::GripperState>
  : std::integral_constant<bool, true> {};

template<>
struct has_bounded_size<robotiq_gripper_interface::msg::GripperState>
  : std::integral_constant<bool, true> {};

template<>
struct is_message<robotiq_gripper_interface::msg::GripperState>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__TRAITS_HPP_
