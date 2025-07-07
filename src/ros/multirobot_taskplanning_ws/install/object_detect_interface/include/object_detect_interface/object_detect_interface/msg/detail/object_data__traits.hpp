// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from object_detect_interface:msg/ObjectData.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__TRAITS_HPP_
#define OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "object_detect_interface/msg/detail/object_data__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'pose'
#include "geometry_msgs/msg/detail/pose__traits.hpp"

namespace object_detect_interface
{

namespace msg
{

inline void to_flow_style_yaml(
  const ObjectData & msg,
  std::ostream & out)
{
  out << "{";
  // member: id
  {
    out << "id: ";
    rosidl_generator_traits::value_to_yaml(msg.id, out);
    out << ", ";
  }

  // member: pose
  {
    out << "pose: ";
    to_flow_style_yaml(msg.pose, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const ObjectData & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "id: ";
    rosidl_generator_traits::value_to_yaml(msg.id, out);
    out << "\n";
  }

  // member: pose
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "pose:\n";
    to_block_style_yaml(msg.pose, out, indentation + 2);
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const ObjectData & msg, bool use_flow_style = false)
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

}  // namespace object_detect_interface

namespace rosidl_generator_traits
{

[[deprecated("use object_detect_interface::msg::to_block_style_yaml() instead")]]
inline void to_yaml(
  const object_detect_interface::msg::ObjectData & msg,
  std::ostream & out, size_t indentation = 0)
{
  object_detect_interface::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use object_detect_interface::msg::to_yaml() instead")]]
inline std::string to_yaml(const object_detect_interface::msg::ObjectData & msg)
{
  return object_detect_interface::msg::to_yaml(msg);
}

template<>
inline const char * data_type<object_detect_interface::msg::ObjectData>()
{
  return "object_detect_interface::msg::ObjectData";
}

template<>
inline const char * name<object_detect_interface::msg::ObjectData>()
{
  return "object_detect_interface/msg/ObjectData";
}

template<>
struct has_fixed_size<object_detect_interface::msg::ObjectData>
  : std::integral_constant<bool, has_fixed_size<geometry_msgs::msg::Pose>::value> {};

template<>
struct has_bounded_size<object_detect_interface::msg::ObjectData>
  : std::integral_constant<bool, has_bounded_size<geometry_msgs::msg::Pose>::value> {};

template<>
struct is_message<object_detect_interface::msg::ObjectData>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__TRAITS_HPP_
