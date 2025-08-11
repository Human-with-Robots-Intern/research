// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice
#include "robot_manager_interface/srv/detail/task_logging__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"

// Include directives for member types
// Member `sub_action`
#include "rosidl_runtime_c/string_functions.h"

bool
robot_manager_interface__srv__TaskLogging_Request__init(robot_manager_interface__srv__TaskLogging_Request * msg)
{
  if (!msg) {
    return false;
  }
  // object_id_a
  // object_id_b
  // instruction
  // sequence_id
  msg->sequence_id = -1;
  // sub_action
  if (!rosidl_runtime_c__String__init(&msg->sub_action)) {
    robot_manager_interface__srv__TaskLogging_Request__fini(msg);
    return false;
  }
  {
    bool success = rosidl_runtime_c__String__assign(&msg->sub_action, "move");
    if (!success) {
      goto abort_init_0;
    }
  }
  // relativity
  msg->relativity = false;
  return true;
abort_init_0:
  return false;
}

void
robot_manager_interface__srv__TaskLogging_Request__fini(robot_manager_interface__srv__TaskLogging_Request * msg)
{
  if (!msg) {
    return;
  }
  // object_id_a
  // object_id_b
  // instruction
  // sequence_id
  // sub_action
  rosidl_runtime_c__String__fini(&msg->sub_action);
  // relativity
}

bool
robot_manager_interface__srv__TaskLogging_Request__are_equal(const robot_manager_interface__srv__TaskLogging_Request * lhs, const robot_manager_interface__srv__TaskLogging_Request * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // object_id_a
  if (lhs->object_id_a != rhs->object_id_a) {
    return false;
  }
  // object_id_b
  if (lhs->object_id_b != rhs->object_id_b) {
    return false;
  }
  // instruction
  if (lhs->instruction != rhs->instruction) {
    return false;
  }
  // sequence_id
  if (lhs->sequence_id != rhs->sequence_id) {
    return false;
  }
  // sub_action
  if (!rosidl_runtime_c__String__are_equal(
      &(lhs->sub_action), &(rhs->sub_action)))
  {
    return false;
  }
  // relativity
  if (lhs->relativity != rhs->relativity) {
    return false;
  }
  return true;
}

bool
robot_manager_interface__srv__TaskLogging_Request__copy(
  const robot_manager_interface__srv__TaskLogging_Request * input,
  robot_manager_interface__srv__TaskLogging_Request * output)
{
  if (!input || !output) {
    return false;
  }
  // object_id_a
  output->object_id_a = input->object_id_a;
  // object_id_b
  output->object_id_b = input->object_id_b;
  // instruction
  output->instruction = input->instruction;
  // sequence_id
  output->sequence_id = input->sequence_id;
  // sub_action
  if (!rosidl_runtime_c__String__copy(
      &(input->sub_action), &(output->sub_action)))
  {
    return false;
  }
  // relativity
  output->relativity = input->relativity;
  return true;
}

robot_manager_interface__srv__TaskLogging_Request *
robot_manager_interface__srv__TaskLogging_Request__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Request * msg = (robot_manager_interface__srv__TaskLogging_Request *)allocator.allocate(sizeof(robot_manager_interface__srv__TaskLogging_Request), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(robot_manager_interface__srv__TaskLogging_Request));
  bool success = robot_manager_interface__srv__TaskLogging_Request__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
robot_manager_interface__srv__TaskLogging_Request__destroy(robot_manager_interface__srv__TaskLogging_Request * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    robot_manager_interface__srv__TaskLogging_Request__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
robot_manager_interface__srv__TaskLogging_Request__Sequence__init(robot_manager_interface__srv__TaskLogging_Request__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Request * data = NULL;

  if (size) {
    data = (robot_manager_interface__srv__TaskLogging_Request *)allocator.zero_allocate(size, sizeof(robot_manager_interface__srv__TaskLogging_Request), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = robot_manager_interface__srv__TaskLogging_Request__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        robot_manager_interface__srv__TaskLogging_Request__fini(&data[i - 1]);
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
robot_manager_interface__srv__TaskLogging_Request__Sequence__fini(robot_manager_interface__srv__TaskLogging_Request__Sequence * array)
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
      robot_manager_interface__srv__TaskLogging_Request__fini(&array->data[i]);
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

robot_manager_interface__srv__TaskLogging_Request__Sequence *
robot_manager_interface__srv__TaskLogging_Request__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Request__Sequence * array = (robot_manager_interface__srv__TaskLogging_Request__Sequence *)allocator.allocate(sizeof(robot_manager_interface__srv__TaskLogging_Request__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = robot_manager_interface__srv__TaskLogging_Request__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
robot_manager_interface__srv__TaskLogging_Request__Sequence__destroy(robot_manager_interface__srv__TaskLogging_Request__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    robot_manager_interface__srv__TaskLogging_Request__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
robot_manager_interface__srv__TaskLogging_Request__Sequence__are_equal(const robot_manager_interface__srv__TaskLogging_Request__Sequence * lhs, const robot_manager_interface__srv__TaskLogging_Request__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!robot_manager_interface__srv__TaskLogging_Request__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
robot_manager_interface__srv__TaskLogging_Request__Sequence__copy(
  const robot_manager_interface__srv__TaskLogging_Request__Sequence * input,
  robot_manager_interface__srv__TaskLogging_Request__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(robot_manager_interface__srv__TaskLogging_Request);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    robot_manager_interface__srv__TaskLogging_Request * data =
      (robot_manager_interface__srv__TaskLogging_Request *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!robot_manager_interface__srv__TaskLogging_Request__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          robot_manager_interface__srv__TaskLogging_Request__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!robot_manager_interface__srv__TaskLogging_Request__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}


bool
robot_manager_interface__srv__TaskLogging_Response__init(robot_manager_interface__srv__TaskLogging_Response * msg)
{
  if (!msg) {
    return false;
  }
  // success
  return true;
}

void
robot_manager_interface__srv__TaskLogging_Response__fini(robot_manager_interface__srv__TaskLogging_Response * msg)
{
  if (!msg) {
    return;
  }
  // success
}

bool
robot_manager_interface__srv__TaskLogging_Response__are_equal(const robot_manager_interface__srv__TaskLogging_Response * lhs, const robot_manager_interface__srv__TaskLogging_Response * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // success
  if (lhs->success != rhs->success) {
    return false;
  }
  return true;
}

bool
robot_manager_interface__srv__TaskLogging_Response__copy(
  const robot_manager_interface__srv__TaskLogging_Response * input,
  robot_manager_interface__srv__TaskLogging_Response * output)
{
  if (!input || !output) {
    return false;
  }
  // success
  output->success = input->success;
  return true;
}

robot_manager_interface__srv__TaskLogging_Response *
robot_manager_interface__srv__TaskLogging_Response__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Response * msg = (robot_manager_interface__srv__TaskLogging_Response *)allocator.allocate(sizeof(robot_manager_interface__srv__TaskLogging_Response), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(robot_manager_interface__srv__TaskLogging_Response));
  bool success = robot_manager_interface__srv__TaskLogging_Response__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
robot_manager_interface__srv__TaskLogging_Response__destroy(robot_manager_interface__srv__TaskLogging_Response * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    robot_manager_interface__srv__TaskLogging_Response__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
robot_manager_interface__srv__TaskLogging_Response__Sequence__init(robot_manager_interface__srv__TaskLogging_Response__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Response * data = NULL;

  if (size) {
    data = (robot_manager_interface__srv__TaskLogging_Response *)allocator.zero_allocate(size, sizeof(robot_manager_interface__srv__TaskLogging_Response), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = robot_manager_interface__srv__TaskLogging_Response__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        robot_manager_interface__srv__TaskLogging_Response__fini(&data[i - 1]);
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
robot_manager_interface__srv__TaskLogging_Response__Sequence__fini(robot_manager_interface__srv__TaskLogging_Response__Sequence * array)
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
      robot_manager_interface__srv__TaskLogging_Response__fini(&array->data[i]);
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

robot_manager_interface__srv__TaskLogging_Response__Sequence *
robot_manager_interface__srv__TaskLogging_Response__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robot_manager_interface__srv__TaskLogging_Response__Sequence * array = (robot_manager_interface__srv__TaskLogging_Response__Sequence *)allocator.allocate(sizeof(robot_manager_interface__srv__TaskLogging_Response__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = robot_manager_interface__srv__TaskLogging_Response__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
robot_manager_interface__srv__TaskLogging_Response__Sequence__destroy(robot_manager_interface__srv__TaskLogging_Response__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    robot_manager_interface__srv__TaskLogging_Response__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
robot_manager_interface__srv__TaskLogging_Response__Sequence__are_equal(const robot_manager_interface__srv__TaskLogging_Response__Sequence * lhs, const robot_manager_interface__srv__TaskLogging_Response__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!robot_manager_interface__srv__TaskLogging_Response__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
robot_manager_interface__srv__TaskLogging_Response__Sequence__copy(
  const robot_manager_interface__srv__TaskLogging_Response__Sequence * input,
  robot_manager_interface__srv__TaskLogging_Response__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(robot_manager_interface__srv__TaskLogging_Response);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    robot_manager_interface__srv__TaskLogging_Response * data =
      (robot_manager_interface__srv__TaskLogging_Response *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!robot_manager_interface__srv__TaskLogging_Response__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          robot_manager_interface__srv__TaskLogging_Response__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!robot_manager_interface__srv__TaskLogging_Response__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
