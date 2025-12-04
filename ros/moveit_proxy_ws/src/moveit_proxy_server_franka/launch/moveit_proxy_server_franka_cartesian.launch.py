import launch
import os
import sys

from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

from ament_index_python.packages import get_package_share_directory

# def get_robot_description():
#     robot_ip_parameter_name = 'robot_ip'
#     use_fake_hardware_parameter_name = 'use_fake_hardware'
#     load_gripper_parameter_name = 'load_gripper'
#     fake_sensor_commands_parameter_name = 'fake_sensor_commands'

#     robot_ip = LaunchConfiguration(robot_ip_parameter_name)
#     use_fake_hardware = LaunchConfiguration(use_fake_hardware_parameter_name)
#     load_gripper = LaunchConfiguration(load_gripper_parameter_name)
#     fake_sensor_commands = LaunchConfiguration(fake_sensor_commands_parameter_name)
	
#     # planning_context
#     franka_xacro_file = os.path.join(get_package_share_directory('franka_description'), 'robots',
#                                      'panda_arm.urdf.xacro')
#     robot_description_config = Command(
#         [FindExecutable(name='xacro'), ' ', franka_xacro_file, ' hand:=', load_gripper,
#          ' robot_ip:=', robot_ip, ' use_fake_hardware:=', use_fake_hardware,
#          ' fake_sensor_commands:=', fake_sensor_commands])

#     robot_description = {'robot_description': robot_description_config}
#     return robot_description

# def get_robot_description_semantic():
#     # MoveIt Configuration
#     robot_ip_parameter_name = 'robot_ip'
#     use_fake_hardware_parameter_name = 'use_fake_hardware'
#     load_gripper_parameter_name = 'load_gripper'
#     fake_sensor_commands_parameter_name = 'fake_sensor_commands'

#     robot_ip = LaunchConfiguration(robot_ip_parameter_name)
#     use_fake_hardware = LaunchConfiguration(use_fake_hardware_parameter_name)
#     load_gripper = LaunchConfiguration(load_gripper_parameter_name)
#     fake_sensor_commands = LaunchConfiguration(fake_sensor_commands_parameter_name)

#     franka_semantic_xacro_file = os.path.join(get_package_share_directory('franka_moveit_config'),
#                                               'srdf',
#                                               'panda_arm.srdf.xacro')
#     robot_description_semantic_config = Command(
#         [FindExecutable(name='xacro'), ' ', franka_semantic_xacro_file, ' hand:=', load_gripper]
#     )
#     robot_description_semantic = {
#         'robot_description_semantic': robot_description_semantic_config
#     }
#     return robot_description_semantic
    
def generate_launch_description():
    # generate_common_hybrid_launch_description() returns a list of nodes to launch
    # robot_description = get_robot_description()
    # robot_description_semantic = get_robot_description_semantic()

    franka_moveit_proxy_server = Node(
        package="moveit_proxy_server_franka",
        namespace="",
        executable="moveit_proxy_server_cartesian_run",
        parameters=[
            {"use_sim_time": True}
        ]
    )
    return launch.LaunchDescription([franka_moveit_proxy_server])
