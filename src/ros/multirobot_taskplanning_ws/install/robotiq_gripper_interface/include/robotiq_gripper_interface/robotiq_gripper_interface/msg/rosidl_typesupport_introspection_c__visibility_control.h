// generated from
// rosidl_typesupport_introspection_c/resource/rosidl_typesupport_introspection_c__visibility_control.h.in
// generated code does not contain a copyright notice

#ifndef ROBOTIQ_GRIPPER_INTERFACE__MSG__ROSIDL_TYPESUPPORT_INTROSPECTION_C__VISIBILITY_CONTROL_H_
#define ROBOTIQ_GRIPPER_INTERFACE__MSG__ROSIDL_TYPESUPPORT_INTROSPECTION_C__VISIBILITY_CONTROL_H_

#ifdef __cplusplus
extern "C"
{
#endif

// This logic was borrowed (then namespaced) from the examples on the gcc wiki:
//     https://gcc.gnu.org/wiki/Visibility

#if defined _WIN32 || defined __CYGWIN__
  #ifdef __GNUC__
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robotiq_gripper_interface __attribute__ ((dllexport))
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_IMPORT_robotiq_gripper_interface __attribute__ ((dllimport))
  #else
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robotiq_gripper_interface __declspec(dllexport)
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_IMPORT_robotiq_gripper_interface __declspec(dllimport)
  #endif
  #ifdef ROSIDL_TYPESUPPORT_INTROSPECTION_C_BUILDING_DLL_robotiq_gripper_interface
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_PUBLIC_robotiq_gripper_interface ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robotiq_gripper_interface
  #else
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_PUBLIC_robotiq_gripper_interface ROSIDL_TYPESUPPORT_INTROSPECTION_C_IMPORT_robotiq_gripper_interface
  #endif
#else
  #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_robotiq_gripper_interface __attribute__ ((visibility("default")))
  #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_IMPORT_robotiq_gripper_interface
  #if __GNUC__ >= 4
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_PUBLIC_robotiq_gripper_interface __attribute__ ((visibility("default")))
  #else
    #define ROSIDL_TYPESUPPORT_INTROSPECTION_C_PUBLIC_robotiq_gripper_interface
  #endif
#endif

#ifdef __cplusplus
}
#endif

#endif  // ROBOTIQ_GRIPPER_INTERFACE__MSG__ROSIDL_TYPESUPPORT_INTROSPECTION_C__VISIBILITY_CONTROL_H_
