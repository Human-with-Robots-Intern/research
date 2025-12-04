cmake_minimum_required(VERSION 3.8)
project(robotiq_gripper)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()


# find dependencies
find_package(ament_cmake REQUIRED)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)
find_package(sensor_msgs REQUIRED) 
find_package(robotiq_gripper_interface REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(rclcpp REQUIRED)


# Find modbus library
find_library(
  MODBUS_LIBRARY
  NAMES modbus libmodbus
  PATHS /usr/lib /usr/lib/x86_64-linux-gnu /usr/local/lib
  REQUIRED
)

add_library(robotiq_gripper_lib SHARED src/robotiq_gripper.cpp)

# Link modbus library
target_link_libraries(robotiq_gripper_lib ${MODBUS_LIBRARY})

# Include directories
target_include_directories(robotiq_gripper_lib PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
  /usr/include
  /usr/local/include
)

target_compile_definitions(robotiq_gripper_lib
  PRIVATE "COMPOSITION_BUILDING_DLL")
ament_target_dependencies(
  robotiq_gripper_lib
  robotiq_gripper_interface
  # modbus
  sensor_msgs
  rclcpp
  rclcpp_components
)

rclcpp_components_register_node(
  robotiq_gripper_lib 
  #PLUGIN "nav2_tutorials_cpp::Nav2ActionClient" 
  # namespace의 범위를 잘못 설정하여 시스템이 실행할 클래스를 찾지 못하는 오류가 발생 하였음. 차후에 이런 실수를 하지 않도록 조심하기 
  PLUGIN "RobotiqGripper" 
  EXECUTABLE robotiq_gripper_run)
#ros2 cli 명령어에서 자동으로 인식할 수 있도록 도와주는 역할인 듯하다...?
# 위 인자를 비활성화 하면 노드를 인식하지 못하는 것을 확인 하였다.

ament_export_targets(robotiq_gripper_lib)
install(TARGETS robotiq_gripper_lib
        EXPORT robotiq_gripper_lib
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
