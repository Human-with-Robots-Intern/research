// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from robotiq_gripper_interface:srv/GetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__BUILDER_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "robotiq_gripper_interface/srv/detail/get_gripper_state_command__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace robotiq_gripper_interface
{

namespace srv
{


}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robotiq_gripper_interface::srv::GetGripperStateCommand_Request>()
{
  return ::robotiq_gripper_interface::srv::GetGripperStateCommand_Request(rosidl_runtime_cpp::MessageInitialization::ZERO);
}

}  // namespace robotiq_gripper_interface


namespace robotiq_gripper_interface
{

namespace srv
{

namespace builder
{

class Init_GetGripperStateCommand_Response_force
{
public:
  explicit Init_GetGripperStateCommand_Response_force(::robotiq_gripper_interface::srv::GetGripperStateCommand_Response & msg)
  : msg_(msg)
  {}
  ::robotiq_gripper_interface::srv::GetGripperStateCommand_Response force(::robotiq_gripper_interface::srv::GetGripperStateCommand_Response::_force_type arg)
  {
    msg_.force = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::GetGripperStateCommand_Response msg_;
};

class Init_GetGripperStateCommand_Response_speed
{
public:
  explicit Init_GetGripperStateCommand_Response_speed(::robotiq_gripper_interface::srv::GetGripperStateCommand_Response & msg)
  : msg_(msg)
  {}
  Init_GetGripperStateCommand_Response_force speed(::robotiq_gripper_interface::srv::GetGripperStateCommand_Response::_speed_type arg)
  {
    msg_.speed = std::move(arg);
    return Init_GetGripperStateCommand_Response_force(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::GetGripperStateCommand_Response msg_;
};

class Init_GetGripperStateCommand_Response_position
{
public:
  Init_GetGripperStateCommand_Response_position()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_GetGripperStateCommand_Response_speed position(::robotiq_gripper_interface::srv::GetGripperStateCommand_Response::_position_type arg)
  {
    msg_.position = std::move(arg);
    return Init_GetGripperStateCommand_Response_speed(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::GetGripperStateCommand_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robotiq_gripper_interface::srv::GetGripperStateCommand_Response>()
{
  return robotiq_gripper_interface::srv::builder::Init_GetGripperStateCommand_Response_position();
}

}  // namespace robotiq_gripper_interface

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__GET_GRIPPER_STATE_COMMAND__BUILDER_HPP_
