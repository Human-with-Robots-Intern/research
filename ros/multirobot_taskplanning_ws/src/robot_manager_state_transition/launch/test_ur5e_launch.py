from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.conditions import IfCondition
from launch.substitutions import PathJoinSubstitution, TextSubstitution, LaunchConfiguration, Command


# # 실제로봇실험
# ros2 launch ur_robot_driver ur_control.launch.py ur_type:=ur5e robot_ip:=192.168.10.11 launch_rviz:=true
# # 중간에 UR5 teaching pendant 에서 외부 조종 프로그램을 구동, 활성화시켜야 함
# ros2 launch ur_moveit_config ur_moveit.launch.py ur_type:=ur5e launch_rviz:=true

# # 시뮬레이션
# ros2 launch ur_robot_driver ur_control.launch.py ur_type:=ur5e robot_ip:=dont-care use_fake_hardware:=true
# ros2 launch ur_moveit_config ur_moveit.launch.py ur_type:=ur5e launch_rviz:=true

def generate_launch_description():
    ur5e_controller = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ur_robot_driver"),
                "launch",
                "ur_control.launch.py"
            ])
        ]),
        launch_arguments={
            "ur_type": "ur5e",
            "robot_ip": "192.168.10.11",
            "launch_rviz": "False",
            # "use_sim_time": "True"
        }.items()
    )

    franka_moveit_core = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ur_moveit_config"),
                "launch",
                "ur_moveit.launch.py"
            ])
        ]),
        launch_arguments={
            "ur_type": "ur5e",
            "launch_rviz": "True",
            # "use_sim_time": "True",
        }.items()
    )

    franka_moveit_proxy_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("moveit_proxy_server_ur5e"),
                "launch",
                "moveit_proxy_server_ur5e_cartesian.launch.py"
            ])
        ])
    )

    robotiq_gripper = Node(
        package="robotiq_gripper",
        namespace="",
        executable="robotiq_gripper_run",
    )

    object_detector = Node(
        package="object_detect_topic",
        namespace="",
        executable="object_detector_11",
    )

    tf_cam = Node(
        package="tf2_ros",
        namespace="",
        executable="static_transform_publisher",
        arguments=[
            "-0.0325",
            "-0.025",
            "0.05",
            "0.0",
            "0.0",
            "0.0",
            "0.1",
            "tool0",
            "cam"
        ],
        remappings=[
          ('/tf', 'tf'),
          ('/tf_static', 'tf_static')
        ]
    )

    # tf_world = Node(
    #     package="tf2_ros",
    #     namespace="",
    #     executable="static_transform_publisher",
    #     arguments=[
    #         "-0.0325",
    #         "-0.025",
    #         "0.05",
    #         "0.0",
    #         "0.0",
    #         "0.0",
    #         "0.1",
    #         "world",
    #         "base_link"
    #     ],
    #     remappings=[
    #       ('/tf', 'tf'),
    #       ('/tf_static', 'tf_static')
    #     ]
    # )
    
    return LaunchDescription([
        ur5e_controller,
        franka_moveit_core,
        franka_moveit_proxy_server,
        robotiq_gripper,
        object_detector,
        tf_cam,
        # tf_world  #
    ])