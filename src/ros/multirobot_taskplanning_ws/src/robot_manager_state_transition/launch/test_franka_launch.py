from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution, TextSubstitution

def generate_launch_description():
    franka_moveit = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("franka_moveit_config"),
                "launch",
                "moveit_edit.launch.py"
            ])
        ]),
        launch_arguments={
            "robot_ip": "172.16.0.2",
            "use_sim_time": "True",
            "load_gripper": "True"
        }.items()
    )
    franka_moveit_proxy_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("moveit_proxy_server_franka"),
                "launch",
                "moveit_proxy_server_franka_cartesian.launch.py"
            ])
        ])
    )
    object_detector = Node(
        package="object_detect_topic",
        namespace="",
        executable="object_detector_15",
    )
    tf_cam = Node(
        package="tf2_ros",
        namespace="",
        executable="static_transform_publisher",
        arguments=[
            "0.010606601717798203",
            "-0.060104076400856556",
            "0.0685",
            "0.0",
            "0.0",
            "0.3826834323650899",
            "0.9238795325112867",
            "panda_link8",
            "cam"
        ],
        remappings=[
          ('/tf', 'tf'),
          ('/tf_static', 'tf_static')
        ]
    )
    tf_world = Node(
        package="tf2_ros",
        namespace="",
        executable="static_transform_publisher",
        arguments=[
            "0.0",
            "0.0",
            "0.0",
            "0.0",
            "0.0",
            "0.0",
            "0.1",
            "world",
            "panda_link0"
        ],
        remappings=[
          ('/tf', 'tf'),
          ('/tf_static', 'tf_static')
        ]
    )

    return LaunchDescription([
        franka_moveit,
        franka_moveit_proxy_server,
        object_detector,
        tf_cam,
        tf_world  
    ])