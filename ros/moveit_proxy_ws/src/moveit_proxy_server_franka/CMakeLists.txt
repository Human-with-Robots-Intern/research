cmake_minimum_required(VERSION 3.8)
project(moveit_proxy_server_franka)
set (CMAKE_CXX_STANDARD 20)
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)
find_package(moveit_proxy_interface REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(rclcpp REQUIRED)

add_library(moveit_proxy_server_franka_lib SHARED src/moveit_proxy_server.cpp)

target_include_directories(moveit_proxy_server_franka_lib PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

target_compile_definitions(moveit_proxy_server_franka_lib
  PRIVATE "COMPOSITION_BUILDING_DLL")
ament_target_dependencies(
  moveit_proxy_server_franka_lib
  moveit_proxy_interface
  moveit_ros_planning_interface 
  rclcpp
  rclcpp_components
)

rclcpp_components_register_node(
  moveit_proxy_server_franka_lib 
  #PLUGIN "nav2_tutorials_cpp::Nav2ActionClient" 
  # namespace의 범위를 잘못 설정하여 시스템이 실행할 클래스를 찾지 못하는 오류가 발생 하였음. 차후에 이런 실수를 하지 않도록 조심하기 
  PLUGIN "MoveitProxyServer" 
  EXECUTABLE moveit_proxy_server_run)
#ros2 cli 명령어에서 자동으로 인식할 수 있도록 도와주는 역할인 듯하다...?
# 위 인자를 비활성화 하면 노드를 인식하지 못하는 것을 확인 하였다.

ament_export_targets(moveit_proxy_server_franka_lib)
install(TARGETS moveit_proxy_server_franka_lib
        EXPORT moveit_proxy_server_franka_lib
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
)

#------------------------

add_library(moveit_proxy_server_franka_cartesian_lib SHARED src/moveit_proxy_server_cartesian.cpp)

target_include_directories(moveit_proxy_server_franka_cartesian_lib PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

target_compile_definitions(moveit_proxy_server_franka_cartesian_lib
  PRIVATE "COMPOSITION_BUILDING_DLL")
ament_target_dependencies(
  moveit_proxy_server_franka_cartesian_lib
  moveit_proxy_interface
  moveit_ros_planning_interface 
  rclcpp
  rclcpp_components
)

rclcpp_components_register_node(
  moveit_proxy_server_franka_cartesian_lib 
  #PLUGIN "nav2_tutorials_cpp::Nav2ActionClient" 
  # namespace의 범위를 잘못 설정하여 시스템이 실행할 클래스를 찾지 못하는 오류가 발생 하였음. 차후에 이런 실수를 하지 않도록 조심하기 
  PLUGIN "MoveitProxyServer" 
  EXECUTABLE moveit_proxy_server_cartesian_run)
#ros2 cli 명령어에서 자동으로 인식할 수 있도록 도와주는 역할인 듯하다...?
# 위 인자를 비활성화 하면 노드를 인식하지 못하는 것을 확인 하였다.

ament_export_targets(moveit_proxy_server_franka_cartesian_lib)
install(TARGETS moveit_proxy_server_franka_cartesian_lib
        EXPORT moveit_proxy_server_franka_cartesian_lib
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
)

#launch 파일 install(share path로 복사)
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}/
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

#------------------------

add_library(moveit_proxy_server_franka_cartesian_and_joint_lib SHARED src/moveit_proxy_server_cartesian_and_joint.cpp)

target_include_directories(moveit_proxy_server_franka_cartesian_and_joint_lib PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

target_compile_definitions(moveit_proxy_server_franka_cartesian_and_joint_lib
  PRIVATE "COMPOSITION_BUILDING_DLL")
ament_target_dependencies(
  moveit_proxy_server_franka_cartesian_and_joint_lib
  moveit_proxy_interface
  moveit_ros_planning_interface 
  rclcpp
  rclcpp_components
)

rclcpp_components_register_node(
  moveit_proxy_server_franka_cartesian_and_joint_lib 
  #PLUGIN "nav2_tutorials_cpp::Nav2ActionClient" 
  # namespace의 범위를 잘못 설정하여 시스템이 실행할 클래스를 찾지 못하는 오류가 발생 하였음. 차후에 이런 실수를 하지 않도록 조심하기 
  PLUGIN "MoveitProxyServer" 
  EXECUTABLE moveit_proxy_server_cartesian_and_joint_run)
#ros2 cli 명령어에서 자동으로 인식할 수 있도록 도와주는 역할인 듯하다...?
# 위 인자를 비활성화 하면 노드를 인식하지 못하는 것을 확인 하였다.

ament_export_targets(moveit_proxy_server_franka_cartesian_and_joint_lib)
install(TARGETS moveit_proxy_server_franka_cartesian_and_joint_lib
        EXPORT moveit_proxy_server_franka_cartesian_and_joint_lib
        ARCHIVE DESTINATION lib
        LIBRARY DESTINATION lib
        RUNTIME DESTINATION bin
)

#launch 파일 install(share path로 복사)
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}/
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