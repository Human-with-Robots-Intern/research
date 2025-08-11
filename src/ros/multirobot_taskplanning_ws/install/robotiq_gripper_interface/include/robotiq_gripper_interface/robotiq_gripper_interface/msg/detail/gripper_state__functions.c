// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
// generated code does not contain a copyright notice
#include "robotiq_gripper_interface/msg/detail/gripper_state__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


bool
robotiq_gripper_interface__msg__GripperState__init(robotiq_gripper_interface__msg__GripperState * msg)
{
  if (!msg) {
    return false;
  }
  // g_act
  // g_gto
  // g_sta
  // g_obj
  // g_flt
  // g_pr
  // g_po
  // g_cu
  return true;
}

void
robotiq_gripper_interface__msg__GripperState__fini(robotiq_gripper_interface__msg__GripperState * msg)
{
  if (!msg) {
    return;
  }
  // g_act
  // g_gto
  // g_sta
  // g_obj
  // g_flt
  // g_pr
  // g_po
  // g_cu
}

bool
robotiq_gripper_interface__msg__GripperState__are_equal(const robotiq_gripper_interface__msg__GripperState * lhs, const robotiq_gripper_interface__msg__GripperState * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // g_act
  if (lhs->g_act != rhs->g_act) {
    return false;
  }
  // g_gto
  if (lhs->g_gto != rhs->g_gto) {
    return false;
  }
  // g_sta
  if (lhs->g_sta != rhs->g_sta) {
    return false;
  }
  // g_obj
  if (lhs->g_obj != rhs->g_obj) {
    return false;
  }
  // g_flt
  if (lhs->g_flt != rhs->g_flt) {
    return false;
  }
  // g_pr
  if (lhs->g_pr != rhs->g_pr) {
    return false;
  }
  // g_po
  if (lhs->g_po != rhs->g_po) {
    return false;
  }
  // g_cu
  if (lhs->g_cu != rhs->g_cu) {
    return false;
  }
  return true;
}

bool
robotiq_gripper_interface__msg__GripperState__copy(
  const robotiq_gripper_interface__msg__GripperState * input,
  robotiq_gripper_interface__msg__GripperState * output)
{
  if (!input || !output) {
    return false;
  }
  // g_act
  output->g_act = input->g_act;
  // g_gto
  output->g_gto = input->g_gto;
  // g_sta
  output->g_sta = input->g_sta;
  // g_obj
  output->g_obj = input->g_obj;
  // g_flt
  output->g_flt = input->g_flt;
  // g_pr
  output->g_pr = input->g_pr;
  // g_po
  output->g_po = input->g_po;
  // g_cu
  output->g_cu = input->g_cu;
  return true;
}

robotiq_gripper_interface__msg__GripperState *
robotiq_gripper_interface__msg__GripperState__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__msg__GripperState * msg = (robotiq_gripper_interface__msg__GripperState *)allocator.allocate(sizeof(robotiq_gripper_interface__msg__GripperState), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(robotiq_gripper_interface__msg__GripperState));
  bool success = robotiq_gripper_interface__msg__GripperState__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
robotiq_gripper_interface__msg__GripperState__destroy(robotiq_gripper_interface__msg__GripperState * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    robotiq_gripper_interface__msg__GripperState__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
robotiq_gripper_interface__msg__GripperState__Sequence__init(robotiq_gripper_interface__msg__GripperState__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__msg__GripperState * data = NULL;

  if (size) {
    data = (robotiq_gripper_interface__msg__GripperState *)allocator.zero_allocate(size, sizeof(robotiq_gripper_interface__msg__GripperState), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = robotiq_gripper_interface__msg__GripperState__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        robotiq_gripper_interface__msg__GripperState__fini(&data[i - 1]);
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
robotiq_gripper_interface__msg__GripperState__Sequence__fini(robotiq_gripper_interface__msg__GripperState__Sequence * array)
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
      robotiq_gripper_interface__msg__GripperState__fini(&array->data[i]);
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

robotiq_gripper_interface__msg__GripperState__Sequence *
robotiq_gripper_interface__msg__GripperState__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  robotiq_gripper_interface__msg__GripperState__Sequence * array = (robotiq_gripper_interface__msg__GripperState__Sequence *)allocator.allocate(sizeof(robotiq_gripper_interface__msg__GripperState__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = robotiq_gripper_interface__msg__GripperState__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
robotiq_gripper_interface__msg__GripperState__Sequence__destroy(robotiq_gripper_interface__msg__GripperState__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    robotiq_gripper_interface__msg__GripperState__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
robotiq_gripper_interface__msg__GripperState__Sequence__are_equal(const robotiq_gripper_interface__msg__GripperState__Sequence * lhs, const robotiq_gripper_interface__msg__GripperState__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!robotiq_gripper_interface__msg__GripperState__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
robotiq_gripper_interface__msg__GripperState__Sequence__copy(
  const robotiq_gripper_interface__msg__GripperState__Sequence * input,
  robotiq_gripper_interface__msg__GripperState__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(robotiq_gripper_interface__msg__GripperState);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    robotiq_gripper_interface__msg__GripperState * data =
      (robotiq_gripper_interface__msg__GripperState *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!robotiq_gripper_interface__msg__GripperState__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          robotiq_gripper_interface__msg__GripperState__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!robotiq_gripper_interface__msg__GripperState__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
