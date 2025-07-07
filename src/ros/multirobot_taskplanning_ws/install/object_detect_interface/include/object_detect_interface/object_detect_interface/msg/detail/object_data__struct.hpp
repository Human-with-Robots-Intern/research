// generated from rosidl_generator_cpp/resource/idl__struct.hpp.em
// with input from object_detect_interface:msg/ObjectData.idl
// generated code does not contain a copyright notice

#ifndef OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_HPP_
#define OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_HPP_

#include <algorithm>
#include <array>
#include <memory>
#include <string>
#include <vector>

#include "rosidl_runtime_cpp/bounded_vector.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


// Include directives for member types
// Member 'pose'
#include "geometry_msgs/msg/detail/pose__struct.hpp"

#ifndef _WIN32
# define DEPRECATED__object_detect_interface__msg__ObjectData __attribute__((deprecated))
#else
# define DEPRECATED__object_detect_interface__msg__ObjectData __declspec(deprecated)
#endif

namespace object_detect_interface
{

namespace msg
{

// message struct
template<class ContainerAllocator>
struct ObjectData_
{
  using Type = ObjectData_<ContainerAllocator>;

  explicit ObjectData_(rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : pose(_init)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->id = 0;
    }
  }

  explicit ObjectData_(const ContainerAllocator & _alloc, rosidl_runtime_cpp::MessageInitialization _init = rosidl_runtime_cpp::MessageInitialization::ALL)
  : pose(_alloc, _init)
  {
    if (rosidl_runtime_cpp::MessageInitialization::ALL == _init ||
      rosidl_runtime_cpp::MessageInitialization::ZERO == _init)
    {
      this->id = 0;
    }
  }

  // field types and members
  using _id_type =
    int16_t;
  _id_type id;
  using _pose_type =
    geometry_msgs::msg::Pose_<ContainerAllocator>;
  _pose_type pose;

  // setters for named parameter idiom
  Type & set__id(
    const int16_t & _arg)
  {
    this->id = _arg;
    return *this;
  }
  Type & set__pose(
    const geometry_msgs::msg::Pose_<ContainerAllocator> & _arg)
  {
    this->pose = _arg;
    return *this;
  }

  // constant declarations

  // pointer types
  using RawPtr =
    object_detect_interface::msg::ObjectData_<ContainerAllocator> *;
  using ConstRawPtr =
    const object_detect_interface::msg::ObjectData_<ContainerAllocator> *;
  using SharedPtr =
    std::shared_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator>>;
  using ConstSharedPtr =
    std::shared_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator> const>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::msg::ObjectData_<ContainerAllocator>>>
  using UniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator>, Deleter>;

  using UniquePtr = UniquePtrWithDeleter<>;

  template<typename Deleter = std::default_delete<
      object_detect_interface::msg::ObjectData_<ContainerAllocator>>>
  using ConstUniquePtrWithDeleter =
    std::unique_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator> const, Deleter>;
  using ConstUniquePtr = ConstUniquePtrWithDeleter<>;

  using WeakPtr =
    std::weak_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator>>;
  using ConstWeakPtr =
    std::weak_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator> const>;

  // pointer types similar to ROS 1, use SharedPtr / ConstSharedPtr instead
  // NOTE: Can't use 'using' here because GNU C++ can't parse attributes properly
  typedef DEPRECATED__object_detect_interface__msg__ObjectData
    std::shared_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator>>
    Ptr;
  typedef DEPRECATED__object_detect_interface__msg__ObjectData
    std::shared_ptr<object_detect_interface::msg::ObjectData_<ContainerAllocator> const>
    ConstPtr;

  // comparison operators
  bool operator==(const ObjectData_ & other) const
  {
    if (this->id != other.id) {
      return false;
    }
    if (this->pose != other.pose) {
      return false;
    }
    return true;
  }
  bool operator!=(const ObjectData_ & other) const
  {
    return !this->operator==(other);
  }
};  // struct ObjectData_

// alias to use template instance with default allocator
using ObjectData =
  object_detect_interface::msg::ObjectData_<std::allocator<void>>;

// constant definitions

}  // namespace msg

}  // namespace object_detect_interface

#endif  // OBJECT_DETECT_INTERFACE__MSG__DETAIL__OBJECT_DATA__STRUCT_HPP_
