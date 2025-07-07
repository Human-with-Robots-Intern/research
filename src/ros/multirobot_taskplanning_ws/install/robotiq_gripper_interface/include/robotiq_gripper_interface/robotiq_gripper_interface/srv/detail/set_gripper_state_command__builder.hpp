// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from robotiq_gripper_interface:srv/SetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__BUILDER_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "robotiq_gripper_interface/srv/detail/set_gripper_state_command__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace robotiq_gripper_interface
{

namespace srv
{

namespace builder
{

class Init_SetGripperStateCommand_Request_force
{
public:
  explicit Init_SetGripperStateCommand_Request_force(::robotiq_gripper_interface::srv::SetGripperStateCommand_Request & msg)
  : msg_(msg)
  {}
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Request force(::robotiq_gripper_interface::srv::SetGripperStateCommand_Request::_force_type arg)
  {
    msg_.force = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Request msg_;
};

class Init_SetGripperStateCommand_Request_speed
{
public:
  explicit Init_SetGripperStateCommand_Request_speed(::robotiq_gripper_interface::srv::SetGripperStateCommand_Request & msg)
  : msg_(msg)
  {}
  Init_SetGripperStateCommand_Request_force speed(::robotiq_gripper_interface::srv::SetGripperStateCommand_Request::_speed_type arg)
  {
    msg_.speed = std::move(arg);
    return Init_SetGripperStateCommand_Request_force(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Request msg_;
};

class Init_SetGripperStateCommand_Request_position
{
public:
  Init_SetGripperStateCommand_Request_position()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_SetGripperStateCommand_Request_speed position(::robotiq_gripper_interface::srv::SetGripperStateCommand_Request::_position_type arg)
  {
    msg_.position = std::move(arg);
    return Init_SetGripperStateCommand_Request_speed(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robotiq_gripper_interface::srv::SetGripperStateCommand_Request>()
{
  return robotiq_gripper_interface::srv::builder::Init_SetGripperStateCommand_Request_position();
}

}  // namespace robotiq_gripper_interface


namespace robotiq_gripper_interface
{

namespace srv
{

namespace builder
{

class Init_SetGripperStateCommand_Response_result
{
public:
  Init_SetGripperStateCommand_Response_result()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Response result(::robotiq_gripper_interface::srv::SetGripperStateCommand_Response::_result_type arg)
  {
    msg_.result = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robotiq_gripper_interface::srv::SetGripperStateCommand_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::robotiq_gripper_interface::srv::SetGripperStateCommand_Response>()
{
  return robotiq_gripper_interface::srv::builder::Init_SetGripperStateCommand_Response_result();
}

}  // namespace robotiq_gripper_interface

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__BUILDER_HPP_
