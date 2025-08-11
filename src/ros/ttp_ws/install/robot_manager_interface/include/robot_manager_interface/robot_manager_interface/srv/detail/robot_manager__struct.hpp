// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from robot_manager_interface:srv/RobotManager.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__robot_manager_interface__srv__RobotManager_Request __attribute__((deprecated))
#else
# define DEPRECATED__robot_manager_interface__srv__RobotManager_Request __declspec(deprecated)
#endif

namespace robot_manager_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct RobotManager_Request_
{
  using Type = RobotManager_Request_<ContainerAllocator>;

  explicit RobotManager_Request_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->robot_model = 0ll;
      this->instruction = 0ll;
      this->a = 0ll;
      this->b = 0ll;
    }
  }

  explicit RobotManager_Request_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->robot_model = 0ll;
      this->instruction = 0ll;
      this->a = 0ll;
      this->b = 0ll;
    }
  }

  // field types and members
  using _robot_model_type =
    int64_t;
  _robot_model_type robot_model;
  using _instruction_type =
    int64_t;
  _instruction_type instruction;
  using _a_type =
    int64_t;
  _a_type a;
  using _b_type =
    int64_t;
  _b_type b;

  // setters for named parameter idiom
  Type & set__robot_model(
    const int64_t & _arg)
  {
    this->robot_model = _arg;
    return *this;
  }
  Type & set__instruction(
    const int64_t & _arg)
  {
    this->instruction = _arg;
    return *this;
  }
  Type & set__a(
    const int64_t & _arg)
  {
    this->a = _arg;
    return *this;
  }
  Type & set__b(
    const int64_t & _arg)
  {
    this->b = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> *;
  using ConstRawPtr =
    const robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robot_manager_interface__srv__RobotManager_Request
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robot_manager_interface__srv__RobotManager_Request
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Request_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const RobotManager_Request_ & other) const
  {
    if (this->robot_model != other.robot_model) {
      return false;
    }
    if (this->instruction != other.instruction) {
      return false;
    }
    if (this->a != other.a) {
      return false;
    }
    if (this->b != other.b) {
      return false;
    }
    return true;
  }
  bool operator!=(const RobotManager_Request_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct RobotManager_Request_

// alias to use template instance with default allocator
using RobotManager_Request =
  robot_manager_interface::srv::RobotManager_Request_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robot_manager_interface


#ifndef _WIN32
# define DEPRECATED__robot_manager_interface__srv__RobotManager_Response __attribute__((deprecated))
#else
# define DEPRECATED__robot_manager_interface__srv__RobotManager_Response __declspec(deprecated)
#endif

namespace robot_manager_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct RobotManager_Response_
{
  using Type = RobotManager_Response_<ContainerAllocator>;

  explicit RobotManager_Response_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->success = false;
    }
  }

  explicit RobotManager_Response_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->success = false;
    }
  }

  // field types and members
  using _success_type =
    bool;
  _success_type success;

  // setters for named parameter idiom
  Type & set__success(
    const bool & _arg)
  {
    this->success = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> *;
  using ConstRawPtr =
    const robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robot_manager_interface__srv__RobotManager_Response
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robot_manager_interface__srv__RobotManager_Response
    std::shared_ptr<robot_manager_interface::srv::RobotManager_Response_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const RobotManager_Response_ & other) const
  {
    if (this->success != other.success) {
      return false;
    }
    return true;
  }
  bool operator!=(const RobotManager_Response_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct RobotManager_Response_

// alias to use template instance with default allocator
using RobotManager_Response =
  robot_manager_interface::srv::RobotManager_Response_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robot_manager_interface

namespace robot_manager_interface
{

namespace srv
{

struct RobotManager
{
  using Request = robot_manager_interface::srv::RobotManager_Request;
  using Response = robot_manager_interface::srv::RobotManager_Response;
};

}  // namespace srv

}  // namespace robot_manager_interface

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__ROBOT_MANAGER__STRUCT_HPP_
