// generated from rosidl_generator_c/resource/idl__functions.h.em
// with input from robotiq_gripper_interface:srv/SetGripperStateCommand.idl
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__FUNCTIONS_H_
#define ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__FUNCTIONS_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stdlib.h>

#include "rosidl_runtime_c/visibility_control.h"
#include "robotiq_gripper_interface/msg/rosidl_generator_c__visibility_control.h"

#include "robotiq_gripper_interface/srv/detail/set_gripper_state_command__struct.h"

/// Initialize srv/SetGripperStateCommand message.
/**
 * If the init function is called twice for the same message without
 * calling fini inbetween previously allocated memory will be leaked.
 * \param[in,out] msg The previously allocated message pointer.
 * Fields without a default value will not be initialized by this function.
 * You might want to call memset(msg, 0, sizeof(
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request
 * )) before or use
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__create()
 * to allocate and initialize the message.
 * \return true if initialization was successful, otherwise false
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg);

/// Finalize srv/SetGripperStateCommand message.
/**
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg);

/// Create srv/SetGripperStateCommand message.
/**
 * It allocates the memory for the message, sets the memory to zero, and
 * calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init().
 * \return The pointer to the initialized message if successful,
 * otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
robotiq_gripper_interface__srv__SetGripperStateCommand_Request *
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__create();

/// Destroy srv/SetGripperStateCommand message.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini()
 * and frees the memory of the message.
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Request * msg);

/// Check for srv/SetGripperStateCommand message equality.
/**
 * \param[in] lhs The message on the left hand size of the equality operator.
 * \param[in] rhs The message on the right hand size of the equality operator.
 * \return true if messages are equal, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * rhs);

/// Copy a srv/SetGripperStateCommand message.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source message pointer.
 * \param[out] output The target message pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer is null
 *   or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Request * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request * output);

/// Initialize array of srv/SetGripperStateCommand messages.
/**
 * It allocates the memory for the number of elements and calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__init()
 * for each element of the array.
 * \param[in,out] array The allocated array pointer.
 * \param[in] size The size / capacity of the array.
 * \return true if initialization was successful, otherwise false
 * If the array pointer is valid and the size is zero it is guaranteed
 # to return true.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array, size_t size);

/// Finalize array of srv/SetGripperStateCommand messages.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__fini()
 * for each element of the array and frees the memory for the number of
 * elements.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array);

/// Create array of srv/SetGripperStateCommand messages.
/**
 * It allocates the memory for the array and calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__init().
 * \param[in] size The size / capacity of the array.
 * \return The pointer to the initialized array if successful, otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence *
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__create(size_t size);

/// Destroy array of srv/SetGripperStateCommand messages.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__fini()
 * on the array,
 * and frees the memory of the array.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * array);

/// Check for srv/SetGripperStateCommand message array equality.
/**
 * \param[in] lhs The message array on the left hand size of the equality operator.
 * \param[in] rhs The message array on the right hand size of the equality operator.
 * \return true if message arrays are equal in size and content, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * rhs);

/// Copy an array of srv/SetGripperStateCommand messages.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source array pointer.
 * \param[out] output The target array pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer
 *   is null or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Request__Sequence * output);

/// Initialize srv/SetGripperStateCommand message.
/**
 * If the init function is called twice for the same message without
 * calling fini inbetween previously allocated memory will be leaked.
 * \param[in,out] msg The previously allocated message pointer.
 * Fields without a default value will not be initialized by this function.
 * You might want to call memset(msg, 0, sizeof(
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response
 * )) before or use
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__create()
 * to allocate and initialize the message.
 * \return true if initialization was successful, otherwise false
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg);

/// Finalize srv/SetGripperStateCommand message.
/**
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg);

/// Create srv/SetGripperStateCommand message.
/**
 * It allocates the memory for the message, sets the memory to zero, and
 * calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init().
 * \return The pointer to the initialized message if successful,
 * otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
robotiq_gripper_interface__srv__SetGripperStateCommand_Response *
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__create();

/// Destroy srv/SetGripperStateCommand message.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini()
 * and frees the memory of the message.
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Response * msg);

/// Check for srv/SetGripperStateCommand message equality.
/**
 * \param[in] lhs The message on the left hand size of the equality operator.
 * \param[in] rhs The message on the right hand size of the equality operator.
 * \return true if messages are equal, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * rhs);

/// Copy a srv/SetGripperStateCommand message.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source message pointer.
 * \param[out] output The target message pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer is null
 *   or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Response * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response * output);

/// Initialize array of srv/SetGripperStateCommand messages.
/**
 * It allocates the memory for the number of elements and calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__init()
 * for each element of the array.
 * \param[in,out] array The allocated array pointer.
 * \param[in] size The size / capacity of the array.
 * \return true if initialization was successful, otherwise false
 * If the array pointer is valid and the size is zero it is guaranteed
 # to return true.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__init(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array, size_t size);

/// Finalize array of srv/SetGripperStateCommand messages.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__fini()
 * for each element of the array and frees the memory for the number of
 * elements.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__fini(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array);

/// Create array of srv/SetGripperStateCommand messages.
/**
 * It allocates the memory for the array and calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__init().
 * \param[in] size The size / capacity of the array.
 * \return The pointer to the initialized array if successful, otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence *
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__create(size_t size);

/// Destroy array of srv/SetGripperStateCommand messages.
/**
 * It calls
 * robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__fini()
 * on the array,
 * and frees the memory of the array.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
void
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__destroy(robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * array);

/// Check for srv/SetGripperStateCommand message array equality.
/**
 * \param[in] lhs The message array on the left hand size of the equality operator.
 * \param[in] rhs The message array on the right hand size of the equality operator.
 * \return true if message arrays are equal in size and content, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__are_equal(const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * lhs, const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * rhs);

/// Copy an array of srv/SetGripperStateCommand messages.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source array pointer.
 * \param[out] output The target array pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer
 *   is null or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_robotiq_gripper_interface
bool
robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence__copy(
  const robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * input,
  robotiq_gripper_interface__srv__SetGripperStateCommand_Response__Sequence * output);

#ifdef __cplusplus
}
#endif

#endif  // ROBOTIQ_GRIPPER_INTERFACE__SRV__DETAIL__SET_GRIPPER_STATE_COMMAND__FUNCTIONS_H_
