from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'robot_manager_state_transition'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*')))
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='kimz1121',
    maintainer_email='kimz1121@naver.com',
    description='robot_manager_state_transition',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robot_manager_service_server_05 = robot_manager_state_transition.robot_manager_service_server_05:main',
            'robot_manager_service_server_05_franka = robot_manager_state_transition.robot_manager_service_server_05_franka:main',
            'robot_manager_service_server_05_franka_gttp_revision = robot_manager_state_transition.robot_manager_service_server_05_franka_gttp_revision:main',
            'robot_manager_service_server_05_ur5e = robot_manager_state_transition.robot_manager_service_server_05_ur5e:main',
            'robot_manager_service_server_05_husky_panda = robot_manager_state_transition.robot_manager_service_server_05_husky_panda:main',
            'robot_manager_service_server_05_jackal = robot_manager_state_transition.robot_manager_service_server_05_jackal:main',
            'robot_manager_service_client_00 = robot_manager_state_transition.robot_manager_service_client_00:main',
            'robot_manager_service_client_01_gttp = robot_manager_state_transition.robot_manager_service_client_01_gttp:main',
            'process_test_node = robot_manager_state_transition.process_test_node:main',
            'process_test_node_gripper = robot_manager_state_transition.process_test_node_gripper:main',
            'process_test_node_detector = robot_manager_state_transition.process_test_node_detector:main',
            'process_test_node_manipulation_with_detector = robot_manager_state_transition.process_test_node_manipulation_with_detector:main',
            'manipulation_test_node = robot_manager_state_transition.manipulation_test_node:main',
            'manipulation_logger_node = robot_manager_state_transition.manipulation_logger_node:main',
            'manipulation_logger_node_ur5e = robot_manager_state_transition.manipulation_logger_node_ur5e:main',
            'manipulation_logger_node_franka = robot_manager_state_transition.manipulation_logger_node_franka:main',
            'manipulation_logger_node_franka_gttp = robot_manager_state_transition.manipulation_logger_node_franka_gttp_revision:main',
        ],
    },
)
