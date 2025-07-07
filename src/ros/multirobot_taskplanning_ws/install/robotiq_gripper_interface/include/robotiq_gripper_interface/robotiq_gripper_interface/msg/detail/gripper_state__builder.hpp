// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__BUILDER_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "robotiq_gripper_interface/msg/detail/gripper_state__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace robotiq_gripper_interface
{

namespace msg
{

namespace builder
{

class Init_GripperState_g_cu
{
public:
  explicit Init_GripperState_g_cu(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  ::robotiq_gripper_interface::msg::GripperState g_cu(::robotiq_gripper_interface::msg::GripperState::_g_cu_type arg)
  {
    msg_.g_cu = std::move(arg);
    return std::move(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_po
{
public:
  explicit Init_GripperState_g_po(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_cu g_po(::robotiq_gripper_interface::msg::GripperState::_g_po_type arg)
  {
    msg_.g_po = std::move(arg);
    return Init_GripperState_g_cu(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_pr
{
public:
  explicit Init_GripperState_g_pr(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_po g_pr(::robotiq_gripper_interface::msg::GripperState::_g_pr_type arg)
  {
    msg_.g_pr = std::move(arg);
    return Init_GripperState_g_po(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_flt
{
public:
  explicit Init_GripperState_g_flt(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_pr g_flt(::robotiq_gripper_interface::msg::GripperState::_g_flt_type arg)
  {
    msg_.g_flt = std::move(arg);
    return Init_GripperState_g_pr(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_obj
{
public:
  explicit Init_GripperState_g_obj(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_flt g_obj(::robotiq_gripper_interface::msg::GripperState::_g_obj_type arg)
  {
    msg_.g_obj = std::move(arg);
    return Init_GripperState_g_flt(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_sta
{
public:
  explicit Init_GripperState_g_sta(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_obj g_sta(::robotiq_gripper_interface::msg::GripperState::_g_sta_type arg)
  {
    msg_.g_sta = std::move(arg);
    return Init_GripperState_g_obj(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_gto
{
public:
  explicit Init_GripperState_g_gto(::robotiq_gripper_interface::msg::GripperState & msg)
  : msg_(msg)
  {}
  Init_GripperState_g_sta g_gto(::robotiq_gripper_interface::msg::GripperState::_g_gto_type arg)
  {
    msg_.g_gto = std::move(arg);
    return Init_GripperState_g_sta(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

class Init_GripperState_g_act
{
public:
  Init_GripperState_g_act()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_GripperState_g_gto g_act(::robotiq_gripper_interface::msg::GripperState::_g_act_type arg)
  {
    msg_.g_act = std::move(arg);
    return Init_GripperState_g_gto(msg_);
  }

private:
  ::robotiq_gripper_interface::msg::GripperState msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::robotiq_gripper_interface::msg::GripperState>()
{
  return robotiq_gripper_interface::msg::builder::Init_GripperState_g_act();
}

}  // namespace robotiq_gripper_interface

#endif  // ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__BUILDER_HPP_
