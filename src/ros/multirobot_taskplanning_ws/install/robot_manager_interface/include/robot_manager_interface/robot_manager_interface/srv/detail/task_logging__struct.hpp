// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice

#ifndef ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_HPP_
#define ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__robot_manager_interface__srv__TaskLogging_Request __attribute__((deprecated))
#else
# define DEPRECATED__robot_manager_interface__srv__TaskLogging_Request __declspec(deprecated)
#endif

namespace robot_manager_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct TaskLogging_Request_
{
  using Type = TaskLogging_Request_<ContainerAllocator>;

  explicit TaskLogging_Request_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::DEFAULTS_ONLY == _init)
    {
      this->sequence_id = -1;
      this->sub_action = "move";
      this->relativity = false;
    } else if (rosidl_runtime_cpp::MessageInitialization::ZERO == _init) {
      this->object_id_a = 0;
      this->object_id_b = 0;
      this->instruction = 0;
      this->sequence_id = 0;
      this->sub_action = "";
      this->relativity = false;
    }
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->object_id_a = 0;
      this->object_id_b = 0;
      this->instruction = 0;
    }
  }

  explicit TaskLogging_Request_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : sub_action(_alloc)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::DEFAULTS_ONLY == _init)
    {
      this->sequence_id = -1;
      this->sub_action = "move";
      this->relativity = false;
    } else if (rosidl_runtime_cpp::MessageInitialization::ZERO == _init) {
      this->object_id_a = 0;
      this->object_id_b = 0;
      this->instruction = 0;
      this->sequence_id = 0;
      this->sub_action = "";
      this->relativity = false;
    }
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->object_id_a = 0;
      this->object_id_b = 0;
      this->instruction = 0;
    }
  }

  // field types and members
  using _object_id_a_type =
    int16_t;
  _object_id_a_type object_id_a;
  using _object_id_b_type =
    int16_t;
  _object_id_b_type object_id_b;
  using _instruction_type =
    int16_t;
  _instruction_type instruction;
  using _sequence_id_type =
    int16_t;
  _sequence_id_type sequence_id;
  using _sub_action_type =
    std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>>;
  _sub_action_type sub_action;
  using _relativity_type =
    bool;
  _relativity_type relativity;

  // setters for named parameter idiom
  Type & set__object_id_a(
    const int16_t & _arg)
  {
    this->object_id_a = _arg;
    return *this;
  }
  Type & set__object_id_b(
    const int16_t & _arg)
  {
    this->object_id_b = _arg;
    return *this;
  }
  Type & set__instruction(
    const int16_t & _arg)
  {
    this->instruction = _arg;
    return *this;
  }
  Type & set__sequence_id(
    const int16_t & _arg)
  {
    this->sequence_id = _arg;
    return *this;
  }
  Type & set__sub_action(
    const std::basic_string<char, std::char_traits<char>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<char>> & _arg)
  {
    this->sub_action = _arg;
    return *this;
  }
  Type & set__relativity(
    const bool & _arg)
  {
    this->relativity = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> *;
  using ConstRawPtr =
    const robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robot_manager_interface__srv__TaskLogging_Request
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robot_manager_interface__srv__TaskLogging_Request
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Request_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const TaskLogging_Request_ & other) const
  {
    if (this->object_id_a != other.object_id_a) {
      return false;
    }
    if (this->object_id_b != other.object_id_b) {
      return false;
    }
    if (this->instruction != other.instruction) {
      return false;
    }
    if (this->sequence_id != other.sequence_id) {
      return false;
    }
    if (this->sub_action != other.sub_action) {
      return false;
    }
    if (this->relativity != other.relativity) {
      return false;
    }
    return true;
  }
  bool operator!=(const TaskLogging_Request_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct TaskLogging_Request_

// alias to use template instance with default allocator
using TaskLogging_Request =
  robot_manager_interface::srv::TaskLogging_Request_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robot_manager_interface


#ifndef _WIN32
# define DEPRECATED__robot_manager_interface__srv__TaskLogging_Response __attribute__((deprecated))
#else
# define DEPRECATED__robot_manager_interface__srv__TaskLogging_Response __declspec(deprecated)
#endif

namespace robot_manager_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct TaskLogging_Response_
{
  using Type = TaskLogging_Response_<ContainerAllocator>;

  explicit TaskLogging_Response_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->success = false;
    }
  }

  explicit TaskLogging_Response_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
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
    robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> *;
  using ConstRawPtr =
    const robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__robot_manager_interface__srv__TaskLogging_Response
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__robot_manager_interface__srv__TaskLogging_Response
    std::shared_ptr<robot_manager_interface::srv::TaskLogging_Response_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const TaskLogging_Response_ & other) const
  {
    if (this->success != other.success) {
      return false;
    }
    return true;
  }
  bool operator!=(const TaskLogging_Response_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct TaskLogging_Response_

// alias to use template instance with default allocator
using TaskLogging_Response =
  robot_manager_interface::srv::TaskLogging_Response_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace robot_manager_interface

namespace robot_manager_interface
{

namespace srv
{

struct TaskLogging
{
  using Request = robot_manager_interface::srv::TaskLogging_Request;
  using Response = robot_manager_interface::srv::TaskLogging_Response;
};

}  // namespace srv

}  // namespace robot_manager_interface

#endif  // ROBOT_MANAGER_INTERFACE__SRV__DETAIL__TASK_LOGGING__STRUCT_HPP_
