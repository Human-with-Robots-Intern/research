// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__robotiq_gripper_interface__msg__GripperState __attribute__((deprecated))
#else
# define DEPRECATED__robotiq_gripper_interface__msg__GripperState __declspec(deprecated)
#endif

namespace robotiq_gripper_interface
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct GripperState_
{
  using Type = GripperState_<ContainerAllocator>;

  explicit GripperState_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->g_act = 0;
      this->g_gto = 0;
      this->g_sta = 0;
      this->g_obj = 0;
      this->g_flt = 0;
      this->g_pr = 0;
      this->g_po = 0;
      this->g_cu = 0;
    }
  }

  explicit GripperState_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->g_act = 0;
      this->g_gto = 0;
      this->g_sta = 0;
      this->g_obj = 0;
      this->g_flt = 0;
      this->g_pr = 0;
      this->g_po = 0;
      this->g_cu = 0;
    }
  }

  // field types and members
  using _g_act_type =
    uint8_t;
  _g_act_type g_act;
  using _g_gto_type =
    uint8_t;
  _g_gto_type g_gto;
  using _g_sta_type =
    uint8_t;
  _g_sta_type g_sta;
  using _g_obj_type =
    uint8_t;
  _g_obj_type g_obj;
  using _g_flt_type =
    uint8_t;
  _g_flt_type g_flt;
  using _g_pr_type =
    uint8_t;
  _g_pr_type g_pr;
  using _g_po_type =
    uint8_t;
  _g_po_type g_po;
  using _g_cu_type =
    uint8_t;
  _g_cu_type g_cu;

  // setters for named parameter idiom
  Type & set__g_act(
    const uint8_t & _arg)
  {
    this->g_act = _arg;
    return *this;
  }
  Type & set__g_gto(
    const uint8_t & _arg)
  {
    this->g_gto = _arg;
    return *this;
  }
  Type & set__g_sta(
    const uint8_t & _arg)
  {
    this->g_sta = _arg;
    return *this;
  }
  Type & set__g_obj(
    const uint8_t & _arg)
  {
    this->g_obj = _arg;
    return *this;
  }
  Type & set__g_flt(
    const uint8_t & _arg)
  {
    this->g_flt = _arg;
    return *this;
  }
  Type & set__g_pr(
    const uint8_t & _arg)
  {
    this->g_pr = _arg;
    return *this;
  }
  Type & set__g_po(
    const uint8_t & _arg)
  {
    this->g_po = _arg;
    return *this;
  }
  Type & set__g_cu(
    const uint8_t & _arg)
  {
    this->g_cu = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> *;
  using ConstRawPtr =
    const robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robotiq_gripper_interface__msg__GripperState
    std::shared_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robotiq_gripper_interface__msg__GripperState
    std::shared_ptr<robotiq_gripper_interface::msg::GripperState_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const GripperState_ & other) const
  {
    if (this->g_act != other.g_act) {
      return false;
    }
    if (this->g_gto != other.g_gto) {
      return false;
    }
    if (this->g_sta != other.g_sta) {
      return false;
    }
    if (this->g_obj != other.g_obj) {
      return false;
    }
    if (this->g_flt != other.g_flt) {
      return false;
    }
    if (this->g_pr != other.g_pr) {
      return false;
    }
    if (this->g_po != other.g_po) {
      return false;
    }
    if (this->g_cu != other.g_cu) {
      return false;
    }
    return true;
  }
  bool operator!=(const GripperState_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct GripperState_

// alias to use template instance with default allocator
using GripperState =
  robotiq_gripper_interface::msg::GripperState_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace robotiq_gripper_interface

#endif  // ROBOTIQ_GRIPPER_INTERFACE__MSG__DETAIL__GRIPPER_STATE__STRUCT_HPP_
