// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from robot_manager_interface:srv/RobotManager.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__BUILDER_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "robot_manager_interface/srv/detail/robot_manager__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace robot_manager_interface
{

namespace srv
{

namespace builder
{

class Init_RobotManager_Request_b
{
public:
  explicit Init_RobotManager_Request_b(::robot_manager_interface::srv::RobotManager_Request & msg)
  : msg_(msg)
  {}
  ::robot_manager_interface::srv::RobotManager_Request b(::robot_manager_interface::srv::RobotManager_Request::_b_type arg)
  {
    msg_.b = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robot_manager_interface::srv::RobotManager_Request msg_;
};

class Init_RobotManager_Request_a
{
public:
  explicit Init_RobotManager_Request_a(::robot_manager_interface::srv::RobotManager_Request & msg)
  : msg_(msg)
  {}
  Init_RobotManager_Request_b a(::robot_manager_interface::srv::RobotManager_Request::_a_type arg)
  {
    msg_.a = std::move(arg);
    return Init_RobotManager_Request_b(msg_);
  }

private:
  ::robot_manager_interface::srv::RobotManager_Request msg_;
};

class Init_RobotManager_Request_instruction
{
public:
  explicit Init_RobotManager_Request_instruction(::robot_manager_interface::srv::RobotManager_Request & msg)
  : msg_(msg)
  {}
  Init_RobotManager_Request_a instruction(::robot_manager_interface::srv::RobotManager_Request::_instruction_type arg)
  {
    msg_.instruction = std::move(arg);
    return Init_RobotManager_Request_a(msg_);
  }

private:
  ::robot_manager_interface::srv::RobotManager_Request msg_;
};

class Init_RobotManager_Request_robot_model
{
public:
  Init_RobotManager_Request_robot_model()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_RobotManager_Request_instruction robot_model(::robot_manager_interface::srv::RobotManager_Request::_robot_model_type arg)
  {
    msg_.robot_model = std::move(arg);
    return Init_RobotManager_Request_instruction(msg_);
  }

private:
  ::robot_manager_interface::srv::RobotManager_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robot_manager_interface::srv::RobotManager_Request>()
{
  return robot_manager_interface::srv::builder::Init_RobotManager_Request_robot_model();
}

}  // namespace robot_manager_interface


namespace robot_manager_interface
{

namespace srv
{

namespace builder
{

class Init_RobotManager_Response_success
{
public:
  Init_RobotManager_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  ::robot_manager_interface::srv::RobotManager_Response success(::robot_manager_interface::srv::RobotManager_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robot_manager_interface::srv::RobotManager_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robot_manager_interface::srv::RobotManager_Response>()
{
  return robot_manager_interface::srv::builder::Init_RobotManager_Response_success();
}

}  // namespace robot_manager_interface

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__BUILDER_HPP_
