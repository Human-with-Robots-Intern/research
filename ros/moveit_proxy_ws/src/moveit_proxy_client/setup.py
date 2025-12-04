from setuptools import find_packages, setup

package_name = 'moveit_proxy_client'

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
    maintainer='lab6',
    maintainer_email='kimz1121@naver.com',
    description='TODO: Package description',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'moveit_proxy_client_run = moveit_proxy_client.proxy_client:main',
            'moveit_proxy_client_user_input_run = moveit_proxy_client.proxy_client_user_input:main',
            'moveit_proxy_client_test_drive_run = moveit_proxy_client.proxy_client_test_drive:main',
        ],
    },
)
