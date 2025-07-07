// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from object_detect_interface:msg/ObjectData.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__BUILDER_HPP_
#define OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "object_detect_interface/msg/detail/object_data__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace object_detect_interface
{

namespace msg
{

namespace builder
{

class Init_ObjectData_pose
{
public:
  explicit Init_ObjectData_pose(::object_detect_interface::msg::ObjectData & msg)
  : msg_(msg)
  {}
  ::object_detect_interface::msg::ObjectData pose(::object_detect_interface::msg::ObjectData::_pose_type arg)
  {
    msg_.pose = std::move(arg);
    return std::move(msg_);
  }

private:
  ::object_detect_interface::msg::ObjectData msg_;
};

class Init_ObjectData_id
{
public:
  Init_ObjectData_id()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ObjectData_pose id(::object_detect_interface::msg::ObjectData::_id_type arg)
  {
    msg_.id = std::move(arg);
    return Init_ObjectData_pose(msg_);
  }

private:
  ::object_detect_interface::msg::ObjectData msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::object_detect_interface::msg::ObjectData>()
{
  return object_detect_interface::msg::builder::Init_ObjectData_id();
}

}  // namespace object_detect_interface

#endif  // OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__BUILDER_HPP_
