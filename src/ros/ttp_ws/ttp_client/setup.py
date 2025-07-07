from setuptools import find_packages, setup

package_name = 'ttp_client'

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
    maintainer='bluebottle',
    maintainer_email='rudxo1997@hanyang.ac.kr',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'ttp_client_communication_test = ttp_client.communication_test:main',
            'ttp_client_ros_communicate_test = ttp_client.ros_communicate:main'
        ],
    },
)
