// generated from rosidl_generator_py/resource/_idl_support.c.em
// with input from robotiq_gripper_interface:msg/GripperState.idl
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
#include "robotiq_gripper_interface/msg/detail/gripper_state__struct.h"
#include "robotiq_gripper_interface/msg/detail/gripper_state__functions.h"


ROSIDL_GENERATOR_C_EXPORT
bool robotiq_gripper_interface__msg__gripper_state__convert_from_py(PyObject * _pymsg, void * _ros_message)
{
  // check that the passed message is of the expected Python class
  {
    char full_classname_dest[58];
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
    assert(strncmp("robotiq_gripper_interface.msg._gripper_state.GripperState", full_classname_dest, 57) == 0);
  }
  robotiq_gripper_interface__msg__GripperState * ros_message = _ros_message;
  {  // g_act
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_act");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_act = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_gto
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_gto");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_gto = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_sta
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_sta");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_sta = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_obj
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_obj");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_obj = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_flt
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_flt");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_flt = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_pr
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_pr");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_pr = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_po
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_po");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_po = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }
  {  // g_cu
    PyObject * field = PyObject_GetAttrString(_pymsg, "g_cu");
    if (!field) {
      return false;
    }
    assert(PyLong_Check(field));
    ros_message->g_cu = (uint8_t)PyLong_AsUnsignedLong(field);
    Py_DECREF(field);
  }

  return true;
}

ROSIDL_GENERATOR_C_EXPORT
PyObject * robotiq_gripper_interface__msg__gripper_state__convert_to_py(void * raw_ros_message)
{
  /* NOTE(esteve): Call constructor of GripperState */
  PyObject * _pymessage = NULL;
  {
    PyObject * pymessage_module = PyImport_ImportModule("robotiq_gripper_interface.msg._gripper_state");
    assert(pymessage_module);
    PyObject * pymessage_class = PyObject_GetAttrString(pymessage_module, "GripperState");
    assert(pymessage_class);
    Py_DECREF(pymessage_module);
    _pymessage = PyObject_CallObject(pymessage_class, NULL);
    Py_DECREF(pymessage_class);
    if (!_pymessage) {
      return NULL;
    }
  }
  robotiq_gripper_interface__msg__GripperState * ros_message = (robotiq_gripper_interface__msg__GripperState *)raw_ros_message;
  {  // g_act
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_act);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_act", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_gto
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_gto);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_gto", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_sta
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_sta);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_sta", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_obj
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_obj);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_obj", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_flt
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_flt);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_flt", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_pr
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_pr);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_pr", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_po
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_po);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_po", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }
  {  // g_cu
    PyObject * field = NULL;
    field = PyLong_FromUnsignedLong(ros_message->g_cu);
    {
      int rc = PyObject_SetAttrString(_pymessage, "g_cu", field);
      Py_DECREF(field);
      if (rc) {
        return NULL;
      }
    }
  }

  // ownership of _pymessage is transferred to the caller
  return _pymessage;
}
