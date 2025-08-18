// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from object_detect_interface:msg/ObjectData.idl
// generated code does not contain a copyright notice
#include "object_detect_interface/msg/detail/object_data__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


// Include directives for member types
// Member `pose`
#include "geometry_msgs/msg/detail/pose__functions.h"

bool
object_detect_interface__msg__ObjectData__init(object_detect_interface__msg__ObjectData * msg)
{
  if (!msg) {
    return false;
  }
  // id
  // pose
  if (!geometry_msgs__msg__Pose__init(&msg->pose)) {
    object_detect_interface__msg__ObjectData__fini(msg);
    return false;
  }
  return true;
}

void
object_detect_interface__msg__ObjectData__fini(object_detect_interface__msg__ObjectData * msg)
{
  if (!msg) {
    return;
  }
  // id
  // pose
  geometry_msgs__msg__Pose__fini(&msg->pose);
}

bool
object_detect_interface__msg__ObjectData__are_equal(const object_detect_interface__msg__ObjectData * lhs, const object_detect_interface__msg__ObjectData * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // id
  if (lhs->id != rhs->id) {
    return false;
  }
  // pose
  if (!geometry_msgs__msg__Pose__are_equal(
      &(lhs->pose), &(rhs->pose)))
  {
    return false;
  }
  return true;
}

bool
object_detect_interface__msg__ObjectData__copy(
  const object_detect_interface__msg__ObjectData * input,
  object_detect_interface__msg__ObjectData * output)
{
  if (!input || !output) {
    return false;
  }
  // id
  output->id = input->id;
  // pose
  if (!geometry_msgs__msg__Pose__copy(
      &(input->pose), &(output->pose)))
  {
    return false;
  }
  return true;
}

object_detect_interface__msg__ObjectData *
object_detect_interface__msg__ObjectData__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  object_detect_interface__msg__ObjectData * msg = (object_detect_interface__msg__ObjectData *)allocator.allocate(sizeof(object_detect_interface__msg__ObjectData), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(object_detect_interface__msg__ObjectData));
  bool success = object_detect_interface__msg__ObjectData__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
object_detect_interface__msg__ObjectData__destroy(object_detect_interface__msg__ObjectData * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    object_detect_interface__msg__ObjectData__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
object_detect_interface__msg__ObjectData__Sequence__init(object_detect_interface__msg__ObjectData__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  object_detect_interface__msg__ObjectData * data = NULL;

  if (size) {
    data = (object_detect_interface__msg__ObjectData *)allocator.zero_allocate(size, sizeof(object_detect_interface__msg__ObjectData), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = object_detect_interface__msg__ObjectData__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        object_detect_interface__msg__ObjectData__fini(&data[i - 1]);
      }
      allocator.deallocate(data, allocator.state);
      return false;
    }
  }
  array->data = data;
  array->size = size;
  array->capacity = size;
  return true;
}

void
object_detect_interface__msg__ObjectData__Sequence__fini(object_detect_interface__msg__ObjectData__Sequence * array)
{
  if (!array) {
    return;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();

  if (array->data) {
    // ensure that data and capacity values are consistent
    assert(array->capacity > 0);
    // finalize all array elements
    for (size_t i = 0; i < array->capacity; ++i) {
      object_detect_interface__msg__ObjectData__fini(&array->data[i]);
    }
    allocator.deallocate(array->data, allocator.state);
    array->data = NULL;
    array->size = 0;
    array->capacity = 0;
  } else {
    // ensure that data, size, and capacity values are consistent
    assert(0 == array->size);
    assert(0 == array->capacity);
  }
}

object_detect_interface__msg__ObjectData__Sequence *
object_detect_interface__msg__ObjectData__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  object_detect_interface__msg__ObjectData__Sequence * array = (object_detect_interface__msg__ObjectData__Sequence *)allocator.allocate(sizeof(object_detect_interface__msg__ObjectData__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = object_detect_interface__msg__ObjectData__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
object_detect_interface__msg__ObjectData__Sequence__destroy(object_detect_interface__msg__ObjectData__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    object_detect_interface__msg__ObjectData__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
object_detect_interface__msg__ObjectData__Sequence__are_equal(const object_detect_interface__msg__ObjectData__Sequence * lhs, const object_detect_interface__msg__ObjectData__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!object_detect_interface__msg__ObjectData__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
object_detect_interface__msg__ObjectData__Sequence__copy(
  const object_detect_interface__msg__ObjectData__Sequence * input,
  object_detect_interface__msg__ObjectData__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(object_detect_interface__msg__ObjectData);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    object_detect_interface__msg__ObjectData * data =
      (object_detect_interface__msg__ObjectData *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!object_detect_interface__msg__ObjectData__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          object_detect_interface__msg__ObjectData__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!object_detect_interface__msg__ObjectData__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
