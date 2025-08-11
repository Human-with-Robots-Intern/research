from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'robot_manager_test'

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
    description='robot_manager_test',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'robot_manager_service_server_test = robot_manager_test.robot_manager_service_server_test:main',
            'robot_manager_service_client_test = robot_manager_test.robot_manager_service_server_test:main',
        ],
    },
)
