// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__BUILDER_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "robot_manager_interface/srv/detail/task_logging__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace robot_manager_interface
{

namespace srv
{

namespace builder
{

class Init_TaskLogging_Request_relativity
{
public:
  explicit Init_TaskLogging_Request_relativity(::robot_manager_interface::srv::TaskLogging_Request & msg)
  : msg_(msg)
  {}
  ::robot_manager_interface::srv::TaskLogging_Request relativity(::robot_manager_interface::srv::TaskLogging_Request::_relativity_type arg)
  {
    msg_.relativity = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

class Init_TaskLogging_Request_sub_action
{
public:
  explicit Init_TaskLogging_Request_sub_action(::robot_manager_interface::srv::TaskLogging_Request & msg)
  : msg_(msg)
  {}
  Init_TaskLogging_Request_relativity sub_action(::robot_manager_interface::srv::TaskLogging_Request::_sub_action_type arg)
  {
    msg_.sub_action = std::move(arg);
    return Init_TaskLogging_Request_relativity(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

class Init_TaskLogging_Request_sequence_id
{
public:
  explicit Init_TaskLogging_Request_sequence_id(::robot_manager_interface::srv::TaskLogging_Request & msg)
  : msg_(msg)
  {}
  Init_TaskLogging_Request_sub_action sequence_id(::robot_manager_interface::srv::TaskLogging_Request::_sequence_id_type arg)
  {
    msg_.sequence_id = std::move(arg);
    return Init_TaskLogging_Request_sub_action(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

class Init_TaskLogging_Request_instruction
{
public:
  explicit Init_TaskLogging_Request_instruction(::robot_manager_interface::srv::TaskLogging_Request & msg)
  : msg_(msg)
  {}
  Init_TaskLogging_Request_sequence_id instruction(::robot_manager_interface::srv::TaskLogging_Request::_instruction_type arg)
  {
    msg_.instruction = std::move(arg);
    return Init_TaskLogging_Request_sequence_id(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

class Init_TaskLogging_Request_object_id_b
{
public:
  explicit Init_TaskLogging_Request_object_id_b(::robot_manager_interface::srv::TaskLogging_Request & msg)
  : msg_(msg)
  {}
  Init_TaskLogging_Request_instruction object_id_b(::robot_manager_interface::srv::TaskLogging_Request::_object_id_b_type arg)
  {
    msg_.object_id_b = std::move(arg);
    return Init_TaskLogging_Request_instruction(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

class Init_TaskLogging_Request_object_id_a
{
public:
  Init_TaskLogging_Request_object_id_a()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_TaskLogging_Request_object_id_b object_id_a(::robot_manager_interface::srv::TaskLogging_Request::_object_id_a_type arg)
  {
    msg_.object_id_a = std::move(arg);
    return Init_TaskLogging_Request_object_id_b(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robot_manager_interface::srv::TaskLogging_Request>()
{
  return robot_manager_interface::srv::builder::Init_TaskLogging_Request_object_id_a();
}

}  // namespace robot_manager_interface


namespace robot_manager_interface
{

namespace srv
{

namespace builder
{

class Init_TaskLogging_Response_success
{
public:
  Init_TaskLogging_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  ::robot_manager_interface::srv::TaskLogging_Response success(::robot_manager_interface::srv::TaskLogging_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robot_manager_interface::srv::TaskLogging_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robot_manager_interface::srv::TaskLogging_Response>()
{
  return robot_manager_interface::srv::builder::Init_TaskLogging_Response_success();
}

}  // namespace robot_manager_interface

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__BUILDER_HPP_
