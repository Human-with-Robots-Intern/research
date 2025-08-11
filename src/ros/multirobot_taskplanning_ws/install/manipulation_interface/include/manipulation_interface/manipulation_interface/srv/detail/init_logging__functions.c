// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from manipulation_interface:srv/InitLogging.idl
// generated code does not contain a copyright notice
#include "manipulation_interface/srv/detail/init_logging__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"

bool
manipulation_interface__srv__InitLogging_Request__init(manipulation_interface__srv__InitLogging_Request * msg)
{
  if (!msg) {
    return false;
  }
  // object_id
  // action_id
  return true;
}

void
manipulation_interface__srv__InitLogging_Request__fini(manipulation_interface__srv__InitLogging_Request * msg)
{
  if (!msg) {
    return;
  }
  // object_id
  // action_id
}

bool
manipulation_interface__srv__InitLogging_Request__are_equal(const manipulation_interface__srv__InitLogging_Request * lhs, const manipulation_interface__srv__InitLogging_Request * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // object_id
  if (lhs->object_id != rhs->object_id) {
    return false;
  }
  // action_id
  if (lhs->action_id != rhs->action_id) {
    return false;
  }
  return true;
}

bool
manipulation_interface__srv__InitLogging_Request__copy(
  const manipulation_interface__srv__InitLogging_Request * input,
  manipulation_interface__srv__InitLogging_Request * output)
{
  if (!input || !output) {
    return false;
  }
  // object_id
  output->object_id = input->object_id;
  // action_id
  output->action_id = input->action_id;
  return true;
}

manipulation_interface__srv__InitLogging_Request *
manipulation_interface__srv__InitLogging_Request__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Request * msg = (manipulation_interface__srv__InitLogging_Request *)allocator.allocate(sizeof(manipulation_interface__srv__InitLogging_Request), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(manipulation_interface__srv__InitLogging_Request));
  bool success = manipulation_interface__srv__InitLogging_Request__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
manipulation_interface__srv__InitLogging_Request__destroy(manipulation_interface__srv__InitLogging_Request * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    manipulation_interface__srv__InitLogging_Request__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
manipulation_interface__srv__InitLogging_Request__Sequence__init(manipulation_interface__srv__InitLogging_Request__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Request * data = NULL;

  if (size) {
    data = (manipulation_interface__srv__InitLogging_Request *)allocator.zero_allocate(size, sizeof(manipulation_interface__srv__InitLogging_Request), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = manipulation_interface__srv__InitLogging_Request__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        manipulation_interface__srv__InitLogging_Request__fini(&data[i - 1]);
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
manipulation_interface__srv__InitLogging_Request__Sequence__fini(manipulation_interface__srv__InitLogging_Request__Sequence * array)
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
      manipulation_interface__srv__InitLogging_Request__fini(&array->data[i]);
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

manipulation_interface__srv__InitLogging_Request__Sequence *
manipulation_interface__srv__InitLogging_Request__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Request__Sequence * array = (manipulation_interface__srv__InitLogging_Request__Sequence *)allocator.allocate(sizeof(manipulation_interface__srv__InitLogging_Request__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = manipulation_interface__srv__InitLogging_Request__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
manipulation_interface__srv__InitLogging_Request__Sequence__destroy(manipulation_interface__srv__InitLogging_Request__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    manipulation_interface__srv__InitLogging_Request__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
manipulation_interface__srv__InitLogging_Request__Sequence__are_equal(const manipulation_interface__srv__InitLogging_Request__Sequence * lhs, const manipulation_interface__srv__InitLogging_Request__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!manipulation_interface__srv__InitLogging_Request__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
manipulation_interface__srv__InitLogging_Request__Sequence__copy(
  const manipulation_interface__srv__InitLogging_Request__Sequence * input,
  manipulation_interface__srv__InitLogging_Request__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(manipulation_interface__srv__InitLogging_Request);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    manipulation_interface__srv__InitLogging_Request * data =
      (manipulation_interface__srv__InitLogging_Request *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!manipulation_interface__srv__InitLogging_Request__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          manipulation_interface__srv__InitLogging_Request__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!manipulation_interface__srv__InitLogging_Request__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}


bool
manipulation_interface__srv__InitLogging_Response__init(manipulation_interface__srv__InitLogging_Response * msg)
{
  if (!msg) {
    return false;
  }
  // success
  return true;
}

void
manipulation_interface__srv__InitLogging_Response__fini(manipulation_interface__srv__InitLogging_Response * msg)
{
  if (!msg) {
    return;
  }
  // success
}

bool
manipulation_interface__srv__InitLogging_Response__are_equal(const manipulation_interface__srv__InitLogging_Response * lhs, const manipulation_interface__srv__InitLogging_Response * rhs)
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
manipulation_interface__srv__InitLogging_Response__copy(
  const manipulation_interface__srv__InitLogging_Response * input,
  manipulation_interface__srv__InitLogging_Response * output)
{
  if (!input || !output) {
    return false;
  }
  // success
  output->success = input->success;
  return true;
}

manipulation_interface__srv__InitLogging_Response *
manipulation_interface__srv__InitLogging_Response__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Response * msg = (manipulation_interface__srv__InitLogging_Response *)allocator.allocate(sizeof(manipulation_interface__srv__InitLogging_Response), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(manipulation_interface__srv__InitLogging_Response));
  bool success = manipulation_interface__srv__InitLogging_Response__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
manipulation_interface__srv__InitLogging_Response__destroy(manipulation_interface__srv__InitLogging_Response * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    manipulation_interface__srv__InitLogging_Response__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
manipulation_interface__srv__InitLogging_Response__Sequence__init(manipulation_interface__srv__InitLogging_Response__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Response * data = NULL;

  if (size) {
    data = (manipulation_interface__srv__InitLogging_Response *)allocator.zero_allocate(size, sizeof(manipulation_interface__srv__InitLogging_Response), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = manipulation_interface__srv__InitLogging_Response__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        manipulation_interface__srv__InitLogging_Response__fini(&data[i - 1]);
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
manipulation_interface__srv__InitLogging_Response__Sequence__fini(manipulation_interface__srv__InitLogging_Response__Sequence * array)
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
      manipulation_interface__srv__InitLogging_Response__fini(&array->data[i]);
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

manipulation_interface__srv__InitLogging_Response__Sequence *
manipulation_interface__srv__InitLogging_Response__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  manipulation_interface__srv__InitLogging_Response__Sequence * array = (manipulation_interface__srv__InitLogging_Response__Sequence *)allocator.allocate(sizeof(manipulation_interface__srv__InitLogging_Response__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = manipulation_interface__srv__InitLogging_Response__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
manipulation_interface__srv__InitLogging_Response__Sequence__destroy(manipulation_interface__srv__InitLogging_Response__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    manipulation_interface__srv__InitLogging_Response__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
manipulation_interface__srv__InitLogging_Response__Sequence__are_equal(const manipulation_interface__srv__InitLogging_Response__Sequence * lhs, const manipulation_interface__srv__InitLogging_Response__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!manipulation_interface__srv__InitLogging_Response__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
manipulation_interface__srv__InitLogging_Response__Sequence__copy(
  const manipulation_interface__srv__InitLogging_Response__Sequence * input,
  manipulation_interface__srv__InitLogging_Response__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(manipulation_interface__srv__InitLogging_Response);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    manipulation_interface__srv__InitLogging_Response * data =
      (manipulation_interface__srv__InitLogging_Response *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!manipulation_interface__srv__InitLogging_Response__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          manipulation_interface__srv__InitLogging_Response__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!manipulation_interface__srv__InitLogging_Response__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
