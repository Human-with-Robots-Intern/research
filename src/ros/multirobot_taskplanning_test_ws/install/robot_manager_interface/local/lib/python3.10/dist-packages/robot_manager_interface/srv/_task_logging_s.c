// generated from rosidl_generator_py/resource/_idl_support.c.em
// with input from robot_manager_interface:srv/TaskLogging.idl
// generated code does not contain a copyright notice
#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
#include <Python.h>
#include <stdbool.h>
#ifndef _WIN32
# pragma GCC diagnostic push
# pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "numpy/ndarrayobject.h"
#ifndef _WIN32
# pragma GCC diagnostic pop
#endif
#include "rosidl_runtime_c/visibility_control.h"
#include "robot_manager_interface/srv/detail/task_logging__struct.h"
#include "robot_manager_interface/srv/detail/task_logging__functions.h"

#include "rosidl_runtime_c/string.h"
#include "rosidl_runtime_c/string_functions.h"


ROSIDL_GENERATOR_C_EXPORT
bool robot_manager_interface__srv__task_logging__request__convert_from_py(PyObject * _pymsg, void * _ros_message)
{
  // check that the passed message is of the expected Python class
  {
    char full_classname_dest[62];
    {
      char * class_name = NULL;
      char * module_name = NULL;
      {
        PyObject * class_attr = PyObject_GetAttrString(_pymsg, "__class__");
        if (class_attr) {
          PyObject * name_attr = PyObject_GetAttrString(class_attr, "__name__");
          if (name_attr) {
            class_name = (char *)PyUnicode_1BYTE_DATA(name_attr);
            Py_DECREF(name_attr);
          }
          PyObject * module_attr = PyObject_GetAttrString(class_attr, "__module__");
          if (module_attr) {
            module_name = (char *)PyUnicode_1BYTE_DATA(module_attr);
            Py_DECREF(module_attr);
          }
          Py_DECREF(class_attr);
        }
      }
      if (!class_name || !module_name) {
        return false;
      }
      snprintf(full_classname_dest, sizeof(full_classname_dest), "%s.%s", module_name, class_name);
    }
    assert(strncmp("robot_manager_interface.srv._task_logging.TaskLogging_Request", full_classname_dest, 61) == 0);
  }
  robot_manager_interface__srv__TaskLogging_Request * ros_message = _ros_message;
  {  // object_id_a
    PyObject * field = PyObject_GetAttrString(_pymsg, "object_id_a");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->object_id_a = (int16_t)PyLong_AsLong(field);
    Py_DECREF(field);
  }
  {  // object_id_b
    PyObject * field = PyObject_GetAttrString(_pymsg, "object_id_b");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->object_id_b = (int16_t)PyLong_AsLong(field);
    Py_DECREF(field);
  }
  {  // instruction
    PyObject * field = PyObject_GetAttrString(_pymsg, "instruction");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->instruction = (int16_t)PyLong_AsLong(field);
    Py_DECREF(field);
  }
  {  // sequence_id
    PyObject * field = PyObject_GetAttrString(_pymsg, "sequence_id");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->sequence_id = (int16_t)PyLong_AsLong(field);
    Py_DECREF(field);
  }
  {  // sub_action
    PyObject * field = PyObject_GetAttrString(_pymsg, "sub_action");
    if (!field) {
      return false;
    }
    assert(PyUnicode_Check(field));
    PyObject * encoded_field = PyUnicode_AsUTF8String(field);
    if (!encoded_field) {
      Py_DECREF(field);
      return false;
    }
    rosidl_runtime_c__String__assign(&ros_message->sub_action, PyBytes_AS_STRING(encoded_field));
    Py_DECREF(encoded_field);
    Py_DECREF(field);
  }
  {  // relativity
    PyObject * field = PyObject_GetAttrString(_pymsg, "relativity");
    if (!field) {
      return false;
    }
    assert(PyBool_Check(field));
    ros_message->relativity = (Py_True == field);
    Py_DECREF(field);
  }

  return true;
}

ROSIDL_GENERATOR_C_EXPORT
PyObject * robot_manager_interface__srv__task_logging__request__convert_to_py(void * raw_ros_message)
{
  /* NOTE(esteve): Call constructor of TaskLogging_Request */
  PyObject * _pymessage = NULL;
  {
    PyObject * pymessage_module = PyImport_ImportModule("robot_manager_interface.srv._task_logging");
    assert(pymessage_module);
    PyObject * pymessage_class = PyObject_GetAttrString(pymessage_module, "TaskLogging_Request");
    assert(pymessage_class);
    Py_DECREF(pymessage_module);
    _pymessage = PyObject_CallObject(pymessage_class, NULL);
    Py_DECREF(pymessage_class);
    if (!_pymessage) {
      return NULL;
    }
  }
  robot_manager_interface__srv__TaskLogging_Request * ros_message = (robot_manager_interface__srv__TaskLogging_Request *)raw_ros_message;
  {  // object_id_a
    PyObject * field = NULL;
    field = PyLong_FromLong(ros_message->object_id_a);
    {
      int rc = PyObject_SetAttrString(_pymessage, "object_id_a", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // object_id_b
    PyObject * field = NULL;
    field = PyLong_FromLong(ros_message->object_id_b);
    {
      int rc = PyObject_SetAttrString(_pymessage, "object_id_b", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // instruction
    PyObject * field = NULL;
    field = PyLong_FromLong(ros_message->instruction);
    {
      int rc = PyObject_SetAttrString(_pymessage, "instruction", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // sequence_id
    PyObject * field = NULL;
    field = PyLong_FromLong(ros_message->sequence_id);
    {
      int rc = PyObject_SetAttrString(_pymessage, "sequence_id", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // sub_action
    PyObject * field = NULL;
    field = PyUnicode_DecodeUTF8(
      ros_message->sub_action.data,
      strlen(ros_message->sub_action.data),
      "replace");
    if (!field) {
      return NULL;
    }
    {
      int rc = PyObject_SetAttrString(_pymessage, "sub_action", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // relativity
    PyObject * field = NULL;
    field = PyBool_FromLong(ros_message->relativity ? 1 : 0);
    {
      int rc = PyObject_SetAttrString(_pymessage, "relativity", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }

  // ownership of _pymessage is transferred to the caller
  return _pymessage;
}

#define NPY_NO_DEPRECATED_API NPY_1_7_API_VERSION
// already included above
// #include <Python.h>
// already included above
// #include <stdbool.h>
// already included above
// #include "numpy/ndarrayobject.h"
// already included above
// #include "rosidl_runtime_c/visibility_control.h"
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__struct.h"
// already included above
// #include "robot_manager_interface/srv/detail/task_logging__functions.h"


ROSIDL_GENERATOR_C_EXPORT
bool robot_manager_interface__srv__task_logging__response__convert_from_py(PyObject * _pymsg, void * _ros_message)
{
  // check that the passed message is of the expected Python class
  {
    char full_classname_dest[63];
    {
      char * class_name = NULL;
      char * module_name = NULL;
      {
        PyObject * class_attr = PyObject_GetAttrString(_pymsg, "__class__");
        if (class_attr) {
          PyObject * name_attr = PyObject_GetAttrString(class_attr, "__name__");
          if (name_attr) {
            class_name = (char *)PyUnicode_1BYTE_DATA(name_attr);
            Py_DECREF(name_attr);
          }
          PyObject * module_attr = PyObject_GetAttrString(class_attr, "__module__");
          if (module_attr) {
            module_name = (char *)PyUnicode_1BYTE_DATA(module_attr);
            Py_DECREF(module_attr);
          }
          Py_DECREF(class_attr);
        }
      }
      if (!class_name || !module_name) {
        return false;
      }
      snprintf(full_classname_dest, sizeof(full_classname_dest), "%s.%s", module_name, class_name);
    }
    assert(strncmp("robot_manager_interface.srv._task_logging.TaskLogging_Response", full_classname_dest, 62) == 0);
  }
  robot_manager_interface__srv__TaskLogging_Response * ros_message = _ros_message;
  {  // success
    PyObject * field = PyObject_GetAttrString(_pymsg, "success");
    if (!field) {
      return false;
    }
    assert(PyBool_Check(field));
    ros_message->success = (Py_True == field);
    Py_DECREF(field);
  }

  return true;
}

ROSIDL_GENERATOR_C_EXPORT
PyObject * robot_manager_interface__srv__task_logging__response__convert_to_py(void * raw_ros_message)
{
  /* NOTE(esteve): Call constructor of TaskLogging_Response */
  PyObject * _pymessage = NULL;
  {
    PyObject * pymessage_module = PyImport_ImportModule("robot_manager_interface.srv._task_logging");
    assert(pymessage_module);
    PyObject * pymessage_class = PyObject_GetAttrString(pymessage_module, "TaskLogging_Response");
    assert(pymessage_class);
    Py_DECREF(pymessage_module);
    _pymessage = PyObject_CallObject(pymessage_class, NULL);
    Py_DECREF(pymessage_class);
    if (!_pymessage) {
      return NULL;
    }
  }
  robot_manager_interface__srv__TaskLogging_Response * ros_message = (robot_manager_interface__srv__TaskLogging_Response *)raw_ros_message;
  {  // success
    PyObject * field = NULL;
    field = PyBool_FromLong(ros_message->success ? 1 : 0);
    {
      int rc = PyObject_SetAttrString(_pymessage, "success", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }

  // ownership of _pymessage is transferred to the caller
  return _pymessage;
}
