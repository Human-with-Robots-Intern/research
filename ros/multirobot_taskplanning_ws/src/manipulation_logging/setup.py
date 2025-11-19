from setuptools import find_packages, setup

package_name = 'manipulation_logging'

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
    maintainer='iw',
    maintainer_email='kimz1121@naver.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'manipulation_offset_logging_run_00 = manipulation_logging.manipulation_offset_logging_00:main',
            'manipulation_offset_logging_run_01 = manipulation_logging.manipulation_offset_logging_01:main',
            'manipulation_offset_logging_run_02 = manipulation_logging.manipulation_offset_logging_02:main',
            'manipulation_offset_logging_run_03 = manipulation_logging.manipulation_offset_logging_03:main',
            'manipulation_offset_logging_run_04 = manipulation_logging.manipulation_offset_logging_04:main',
            'manipulation_offset_logging_test_run = manipulation_logging.manipulation_offset_logging_test:main'
        ],
    },
)
