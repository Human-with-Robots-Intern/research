from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'object_detect_topic'

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
            "object_detector = object_detect_topic.object_detector_02:main",
            "object_detector_03 = object_detect_topic.object_detector_03:main",
            "object_detector_04 = object_detect_topic.object_detector_04:main",
            "object_detector_05 = object_detect_topic.object_detector_05:main",
            "object_detector_06 = object_detect_topic.object_detector_06:main",
            "object_detector_07 = object_detect_topic.object_detector_07:main",
            "object_detector_08 = object_detect_topic.object_detector_08:main",
            "object_detector_09 = object_detect_topic.object_detector_09:main",
            "object_detector_10 = object_detect_topic.object_detector_10:main",
            "object_detector_11 = object_detect_topic.object_detector_11:main",
            "object_detector_12 = object_detect_topic.object_detector_12:main",
            "object_detector_13 = object_detect_topic.object_detector_13:main", #0~360도 두배해서 계산
            "object_detector_14 = object_detect_topic.object_detector_14:main", #sine cose으로 변환해서 벡터로 계산
            "object_detector_15 = object_detect_topic.object_detector_15:main" #sine cose으로 변환해서 벡터로 계산
        ],
    },
)
