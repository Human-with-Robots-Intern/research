from setuptools import find_packages, setup

package_name = 'nav_client_python'

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
    maintainer_email='lab6@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'nav_client_python_run = nav_client_python.nav2_action_client:main',
            'nav_client_python_run_desk = nav_client_python.nav2_action_client_desk:main',
            'nav_client_python_run_kitchen_cabinet = nav_client_python.nav2_action_client_kitchen_cabinet:main',
            'nav_client_python_run_kitchen_table = nav_client_python.nav2_action_client_kitchen_table:main',
            'nav_client_python_run_origin = nav_client_python.nav2_action_client_origin:main',
            'nav_client_python_run_01 = nav_client_python.nav2_action_client_01:main',
            'nav_client_python_run_02 = nav_client_python.nav2_action_client_02:main'
        ],
    },
)
