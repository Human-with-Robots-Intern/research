from setuptools import find_packages, setup

package_name = 'robot_manager'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='KHJ',
    maintainer_email='june2450@naver.com',
    description='robot_manager',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robot_manager_service_client_00 = robot_manager.robot_manager_service_client_00:main',
            'robot_manager_service_client_realtime_00 = robot_manager.robot_manager_service_client_realtime_00:main',
            'robot_manager_service_server_00 = robot_manager.robot_manager_service_server_00:main'
        ],
    },
)
