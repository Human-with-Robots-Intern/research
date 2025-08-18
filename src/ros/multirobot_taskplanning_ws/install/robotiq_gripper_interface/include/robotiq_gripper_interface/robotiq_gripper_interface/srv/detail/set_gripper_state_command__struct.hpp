// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from robotiq_gripper_interface:srv/SetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__STRUCT_HPP_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Request __attribute__((deprecated))
#else
# define DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Request __declspec(deprecated)
#endif

namespace robotiq_gripper_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct SetGripperStateCommand_Request_
{
  using Type = SetGripperStateCommand_Request_<ContainerAllocator>;

  explicit SetGripperStateCommand_Request_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->position = 0.0f;
      this->speed = 0.0f;
      this->force = 0.0f;
    }
  }

  explicit SetGripperStateCommand_Request_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->position = 0.0f;
      this->speed = 0.0f;
      this->force = 0.0f;
    }
  }

  // field types and members
  using _position_type =
    float;
  _position_type position;
  using _speed_type =
    float;
  _speed_type speed;
  using _force_type =
    float;
  _force_type force;

  // setters for named parameter idiom
  Type & set__position(
    const float & _arg)
  {
    this->position = _arg;
    return *this;
  }
  Type & set__speed(
    const float & _arg)
  {
    this->speed = _arg;
    return *this;
  }
  Type & set__force(
    const float & _arg)
  {
    this->force = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> *;
  using ConstRawPtr =
    const robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Request
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Request
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const SetGripperStateCommand_Request_ & other) const
  {
    if (this->position != other.position) {
      return false;
    }
    if (this->speed != other.speed) {
      return false;
    }
    if (this->force != other.force) {
      return false;
    }
    return true;
  }
  bool operator!=(const SetGripperStateCommand_Request_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct SetGripperStateCommand_Request_

// alias to use template instance with default allocator
using SetGripperStateCommand_Request =
  robotiq_gripper_interface::srv::SetGripperStateCommand_Request_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robotiq_gripper_interface


#ifndef _WIN32
# define DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Response __attribute__((deprecated))
#else
# define DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Response __declspec(deprecated)
#endif

namespace robotiq_gripper_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct SetGripperStateCommand_Response_
{
  using Type = SetGripperStateCommand_Response_<ContainerAllocator>;

  explicit SetGripperStateCommand_Response_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->result = false;
    }
  }

  explicit SetGripperStateCommand_Response_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->result = false;
    }
  }

  // field types and members
  using _result_type =
    bool;
  _result_type result;

  // setters for named parameter idiom
  Type & set__result(
    const bool & _arg)
  {
    this->result = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> *;
  using ConstRawPtr =
    const robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Response
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robotiq_gripper_interface__srv__SetGripperStateCommand_Response
    std::shared_ptr<robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const SetGripperStateCommand_Response_ & other) const
  {
    if (this->result != other.result) {
      return false;
    }
    return true;
  }
  bool operator!=(const SetGripperStateCommand_Response_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct SetGripperStateCommand_Response_

// alias to use template instance with default allocator
using SetGripperStateCommand_Response =
  robotiq_gripper_interface::srv::SetGripperStateCommand_Response_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robotiq_gripper_interface

namespace robotiq_gripper_interface
{

namespace srv
{

struct SetGripperStateCommand
{
  using Request = robotiq_gripper_interface::srv::SetGripperStateCommand_Request;
  using Response = robotiq_gripper_interface::srv::SetGripperStateCommand_Response;
};

}  // namespace srv

}  // namespace robotiq_gripper_interface

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__STRUCT_HPP_
