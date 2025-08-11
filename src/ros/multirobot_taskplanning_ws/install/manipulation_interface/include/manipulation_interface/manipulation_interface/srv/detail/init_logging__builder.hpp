// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from manipulation_interface:srv/InitLogging.idl
// generated code does not contain a copyright notice

#ifndef MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__BUILDER_HPP_
#define MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "manipulation_interface/srv/detail/init_logging__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace manipulation_interface
{

namespace srv
{

namespace builder
{

class Init_InitLogging_Request_action_id
{
public:
  explicit Init_InitLogging_Request_action_id(::manipulation_interface::srv::InitLogging_Request & msg)
  : msg_(msg)
  {}
  ::manipulation_interface::srv::InitLogging_Request action_id(::manipulation_interface::srv::InitLogging_Request::_action_id_type arg)
  {
    msg_.action_id = std::move(arg);
    return std::move(msg_);
  }

private:
  ::manipulation_interface::srv::InitLogging_Request msg_;
};

class Init_InitLogging_Request_object_id
{
public:
  Init_InitLogging_Request_object_id()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_InitLogging_Request_action_id object_id(::manipulation_interface::srv::InitLogging_Request::_object_id_type arg)
  {
    msg_.object_id = std::move(arg);
    return Init_InitLogging_Request_action_id(msg_);
  }

private:
  ::manipulation_interface::srv::InitLogging_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::manipulation_interface::srv::InitLogging_Request>()
{
  return manipulation_interface::srv::builder::Init_InitLogging_Request_object_id();
}

}  // namespace manipulation_interface


namespace manipulation_interface
{

namespace srv
{

namespace builder
{

class Init_InitLogging_Response_success
{
public:
  Init_InitLogging_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  ::manipulation_interface::srv::InitLogging_Response success(::manipulation_interface::srv::InitLogging_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return std::move(msg_);
  }

private:
  ::manipulation_interface::srv::InitLogging_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::manipulation_interface::srv::InitLogging_Response>()
{
  return manipulation_interface::srv::builder::Init_InitLogging_Response_success();
}

}  // namespace manipulation_interface

#endif  // MANIPULATION_INTERFACE__SRV__DETAIL__INIT_LOGGING__BUILDER_HPP_
