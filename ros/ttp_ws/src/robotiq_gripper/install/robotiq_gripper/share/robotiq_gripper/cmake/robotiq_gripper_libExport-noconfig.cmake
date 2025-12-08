#----------------------------------------------------------------
# Generated CMake target import file.
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "robotiq_gripper::robotiq_gripper_lib" for configuration ""
set_property(TARGET robotiq_gripper::robotiq_gripper_lib APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(robotiq_gripper::robotiq_gripper_lib PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/librobotiq_gripper_lib.so"
  IMPORTED_SONAME_NOCONFIG "librobotiq_gripper_lib.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS robotiq_gripper::robotiq_gripper_lib )
list(APPEND _IMPORT_CHECK_FILES_FOR_robotiq_gripper::robotiq_gripper_lib "${_IMPORT_PREFIX}/lib/librobotiq_gripper_lib.so" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
