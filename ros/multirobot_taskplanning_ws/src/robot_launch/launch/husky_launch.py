from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution, TextSubstitution

def generate_launch_description():
    
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                PathJoinSubstitution([
                    FindPackageShare('franka_moveit_config'),
                    'launch',
                    'moveit_edit.launch.py'
                ])
            ]),
            launch_arguments={
                'hostname': '172.16.0.161',
                'min_ang': '-1.570796327',
                'max_ang': '1.570796327'
            }.items()
        ),
        Node(
            package='object_detect',
            namespace='',
            executable='object_detector_07',
            name='sim'
        ),
        Node(
            package='moveit_proxy_server_franka',
            namespace='',
            executable='moveit_proxy_server_cartesian_run',
            name='sim'
        ),
        Node(
            package='general_client_python',
            namespace='/a200_0000',
            executable='general_client_node_11',
            name='sim'
        ),

    ])