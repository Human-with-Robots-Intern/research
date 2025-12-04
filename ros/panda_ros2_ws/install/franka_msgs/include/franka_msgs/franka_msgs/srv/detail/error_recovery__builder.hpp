// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from franka_msgs:srv/ErrorRecovery.idl
// generated code does not contain a copyright notice

#ifndef FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__BUILDER_HPP_
#define FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "franka_msgs/srv/detail/error_recovery__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace franka_msgs
{

namespace srv
{


}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::franka_msgs::srv::ErrorRecovery_Request>()
{
  return ::franka_msgs::srv::ErrorRecovery_Request(rosidl_runtime_cpp::MessageInitialization::ZERO);
}

}  // namespace franka_msgs


namespace franka_msgs
{

namespace srv
{

namespace builder
{

class Init_ErrorRecovery_Response_error
{
public:
  explicit Init_ErrorRecovery_Response_error(::franka_msgs::srv::ErrorRecovery_Response & msg)
  : msg_(msg)
  {}
  ::franka_msgs::srv::ErrorRecovery_Response error(::franka_msgs::srv::ErrorRecovery_Response::_error_type arg)
  {
    msg_.error = std::move(arg);
    return std::move(msg_);
  }

private:
  ::franka_msgs::srv::ErrorRecovery_Response msg_;
};

class Init_ErrorRecovery_Response_success
{
public:
  Init_ErrorRecovery_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_ErrorRecovery_Response_error success(::franka_msgs::srv::ErrorRecovery_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return Init_ErrorRecovery_Response_error(msg_);
  }

private:
  ::franka_msgs::srv::ErrorRecovery_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::franka_msgs::srv::ErrorRecovery_Response>()
{
  return franka_msgs::srv::builder::Init_ErrorRecovery_Response_success();
}

}  // namespace franka_msgs

#endif  // FRANKA_MSGS__SRV__DETAIL__ERROR_RECOVERY__BUILDER_HPP_
