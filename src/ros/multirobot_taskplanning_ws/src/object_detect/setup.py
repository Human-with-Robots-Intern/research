from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'object_detect'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('lib', package_name, 'module'), glob(os.path.join('module', '*.py')))
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='administrator',
    maintainer_email='kimz1121@naver.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            "object_detector = object_detect.object_detector_02:main",
            "object_detector_03 = object_detect.object_detector_03:main",
            "object_detector_04 = object_detect.object_detector_04:main",
            "object_detector_05 = object_detect.object_detector_05:main",
            "object_detector_06 = object_detect.object_detector_06:main",
            "object_detector_07 = object_detect.object_detector_07:main",
            "object_detector_08 = object_detect.object_detector_08:main",
            "object_detector_09 = object_detect.object_detector_09:main"
        ],
    },
)
