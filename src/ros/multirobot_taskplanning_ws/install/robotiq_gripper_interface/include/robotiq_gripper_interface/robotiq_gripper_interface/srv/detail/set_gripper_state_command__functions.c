// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from robotiq_gripper_interface:srv/SetGripperStateCommand.idl
// generated code does not contain a copyright notice
#include "robotiq_gripper_interface/srv/detail/set_gripper_state_command__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg)
{
  if (!msg) {
    return false;
  }
  // position
  // speed
  // force
  return true;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg)
{
  if (!msg) {
    return;
  }
  // position
  // speed
  // force
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // position
  if (lhs->position != rhs->position) {
    return false;
  }
  // speed
  if (lhs->speed != rhs->speed) {
    return false;
  }
  // force
  if (lhs->force != rhs->force) {
    return false;
  }
  return true;
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request * output)
{
  if (!input || !output) {
    return false;
  }
  // position
  output->position = input->position;
  // speed
  output->speed = input->speed;
  // force
  output->force = input->force;
  return true;
}

robotiq_gripper_interface__srv__SetGripperStateCommand_Request *
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg = (robotiq_gripper_interface__srv__SetGripperStateCommand_Request *)allocator.allocate(sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Request), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Request));
  bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request * data = NULL;

  if (size) {
    data = (robotiq_gripper_interface__srv__SetGripperStateCommand_Request *)allocator.zero_allocate(size, sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Request), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(&data[i - 1]);
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
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array)
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
      robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(&array->data[i]);
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

robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence *
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array = (robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence *)allocator.allocate(sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Request__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Request);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    robotiq_gripper_interface__srv__SetGripperStateCommand_Request * data =
      (robotiq_gripper_interface__srv__SetGripperStateCommand_Request *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Request__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}


bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg)
{
  if (!msg) {
    return false;
  }
  // result
  return true;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg)
{
  if (!msg) {
    return;
  }
  // result
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // result
  if (lhs->result != rhs->result) {
    return false;
  }
  return true;
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response * output)
{
  if (!input || !output) {
    return false;
  }
  // result
  output->result = input->result;
  return true;
}

robotiq_gripper_interface__srv__SetGripperStateCommand_Response *
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg = (robotiq_gripper_interface__srv__SetGripperStateCommand_Response *)allocator.allocate(sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Response), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Response));
  bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response * data = NULL;

  if (size) {
    data = (robotiq_gripper_interface__srv__SetGripperStateCommand_Response *)allocator.zero_allocate(size, sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Response), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(&data[i - 1]);
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
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array)
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
      robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(&array->data[i]);
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

robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence *
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array = (robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence *)allocator.allocate(sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Response__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(robotiq_gripper_interface__srv__SetGripperStateCommand_Response);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    robotiq_gripper_interface__srv__SetGripperStateCommand_Response * data =
      (robotiq_gripper_interface__srv__SetGripperStateCommand_Response *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!robotiq_gripper_interface__srv__SetGripperStateCommand_Response__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
