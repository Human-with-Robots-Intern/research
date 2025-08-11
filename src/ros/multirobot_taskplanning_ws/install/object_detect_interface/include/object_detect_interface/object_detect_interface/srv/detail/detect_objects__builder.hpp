// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__BUILDER_HPP_
#define OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "object_detect_interface/srv/detail/detect_objects__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace object_detect_interface
{

namespace srv
{


}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::object_detect_interface::srv::DetectObjects_Request>()
{
  return ::object_detect_interface::srv::DetectObjects_Request(rosidl_runtime_cpp::MessageInitialization::ZERO);
}

}  // namespace object_detect_interface


namespace object_detect_interface
{

namespace srv
{

namespace builder
{

class Init_DetectObjects_Response_object_list
{
public:
  explicit Init_DetectObjects_Response_object_list(::object_detect_interface::srv::DetectObjects_Response & msg)
  : msg_(msg)
  {}
  ::object_detect_interface::srv::DetectObjects_Response object_list(::object_detect_interface::srv::DetectObjects_Response::_object_list_type arg)
  {
    msg_.object_list = std::move(arg);
    return std::move(msg_);
  }

private:
  ::object_detect_interface::srv::DetectObjects_Response msg_;
};

class Init_DetectObjects_Response_entity_num
{
public:
  Init_DetectObjects_Response_entity_num()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_DetectObjects_Response_object_list entity_num(::object_detect_interface::srv::DetectObjects_Response::_entity_num_type arg)
  {
    msg_.entity_num = std::move(arg);
    return Init_DetectObjects_Response_object_list(msg_);
  }

private:
  ::object_detect_interface::srv::DetectObjects_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::object_detect_interface::srv::DetectObjects_Response>()
{
  return object_detect_interface::srv::builder::Init_DetectObjects_Response_entity_num();
}

}  // namespace object_detect_interface

#endif  // OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__BUILDER_HPP_
