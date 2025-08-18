// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from object_detect_interface:srv/DetectObjects.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_HPP_
#define OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


#ifndef _WIN32
# define DEPRECATED__object_detect_interface__srv__DetectObjects_Request __attribute__((deprecated))
#else
# define DEPRECATED__object_detect_interface__srv__DetectObjects_Request __declspec(deprecated)
#endif

namespace object_detect_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct DetectObjects_Request_
{
  using Type = DetectObjects_Request_<ContainerAllocator>;

  explicit DetectObjects_Request_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->structure_needs_at_least_one_member = 0;
    }
  }

  explicit DetectObjects_Request_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->structure_needs_at_least_one_member = 0;
    }
  }

  // field types and members
  using _structure_needs_at_least_one_member_type =
    uint8_t;
  _structure_needs_at_least_one_member_type structure_needs_at_least_one_member;


  // constant declarations

  // pointer types
  using RawPtr =
    object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> *;
  using ConstRawPtr =
    const object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__object_detect_interface__srv__DetectObjects_Request
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__object_detect_interface__srv__DetectObjects_Request
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Request_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const DetectObjects_Request_ & other) const
  {
    if (this->structure_needs_at_least_one_member != other.structure_needs_at_least_one_member) {
      return false;
    }
    return true;
  }
  bool operator!=(const DetectObjects_Request_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct DetectObjects_Request_

// alias to use template instance with default allocator
using DetectObjects_Request =
  object_detect_interface::srv::DetectObjects_Request_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace object_detect_interface


// Include directives for member types
// Member 'object_list'
#include "object_detect_interface/msg/detail/object_data__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__object_detect_interface__srv__DetectObjects_Response __attribute__((deprecated))
#else
# define DEPRECATED__object_detect_interface__srv__DetectObjects_Response __declspec(deprecated)
#endif

namespace object_detect_interface
{

namespace srv
{

// message struct
template<class ContainerAllocator>
struct DetectObjects_Response_
{
  using Type = DetectObjects_Response_<ContainerAllocator>;

  explicit DetectObjects_Response_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->entity_num = 0;
    }
  }

  explicit DetectObjects_Response_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  {
    (void)_alloc;
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->entity_num = 0;
    }
  }

  // field types and members
  using _entity_num_type =
    int16_t;
  _entity_num_type entity_num;
  using _object_list_type =
    std::vector<object_detect_interface::msg::ObjectData_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<object_detect_interface::msg::ObjectData_<ContainerAllocator>>>;
  _object_list_type object_list;

  // setters for named parameter idiom
  Type & set__entity_num(
    const int16_t & _arg)
  {
    this->entity_num = _arg;
    return *this;
  }
  Type & set__object_list(
    const std::vector<object_detect_interface::msg::ObjectData_<ContainerAllocator>, typename std::allocator_traits<ContainerAllocator>::template rebind_alloc<object_detect_interface::msg::ObjectData_<ContainerAllocator>>> & _arg)
  {
    this->object_list = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> *;
  using ConstRawPtr =
    const object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__object_detect_interface__srv__DetectObjects_Response
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__object_detect_interface__srv__DetectObjects_Response
    std::shared_ptr<object_detect_interface::srv::DetectObjects_Response_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const DetectObjects_Response_ & other) const
  {
    if (this->entity_num != other.entity_num) {
      return false;
    }
    if (this->object_list != other.object_list) {
      return false;
    }
    return true;
  }
  bool operator!=(const DetectObjects_Response_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct DetectObjects_Response_

// alias to use template instance with default allocator
using DetectObjects_Response =
  object_detect_interface::srv::DetectObjects_Response_<std::allocator<void>>;

// constant definitions

}  // namespace srv

}  // namespace object_detect_interface

namespace object_detect_interface
{

namespace srv
{

struct DetectObjects
{
  using Request = object_detect_interface::srv::DetectObjects_Request;
  using Response = object_detect_interface::srv::DetectObjects_Response;
};

}  // namespace srv

}  // namespace object_detect_interface

#endif  // OBJECT_DETECT_INTERFACE__SRV__DETAIL__DETECT_OBJECTS__STRUCT_HPP_
