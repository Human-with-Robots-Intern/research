import gymnasium as gym
import numpy as np
import torch as th

import omnigibson as og
import omnigibson.lazy as lazy
import omnigibson.utils.transform_utils as T


from omnigibson.object_states.open_state import _get_relevant_joints
from omnigibson.utils.constants import JointAxis, JointType

from omnigibson.utils.python_utils import multi_dim_linspace
from omnigibson.utils.ui_utils import create_module_logger


def interpolate_waypoints_toggle(start_pose, end_pose, num_waypoints="default"):
    """
    Interpolates a series of waypoints between a start and end pose.

    Args:
        start_pose (tuple): A tuple containing the starting position and orientation as a quaternion.
        end_pose (tuple): A tuple containing the ending position and orientation as a quaternion.
        num_waypoints (int, optional): The number of waypoints to interpolate. If "default", the number of waypoints is calculated based on the distance between the start and end pose.

    Returns:
        list: A list of tuples representing the interpolated waypoints, where each tuple contains a position and orientation as a quaternion.
    """
    #
    start_pos, start_orn = start_pose
    end_pos, end_orn = end_pose
    travel_distance = th.norm(end_pos - start_pos)

    if num_waypoints == "default":
        num_waypoints = th.max(th.tensor([2, int(travel_distance / 0.01) + 1])).item()

    pos_waypoints = multi_dim_linspace(start_pos, end_pos, num_waypoints)

    t_values = th.linspace(0, 1, num_waypoints)
    # Also interpolate the rotations

    quat_waypoints = [T.quat_slerp(start_orn, end_orn, t) for t in t_values]

    return [waypoint for waypoint in zip(pos_waypoints, quat_waypoints)]


def toggle_position_for_toggle_on_prismatic_joint(
    robot, toggle_obj, relevant_joint, should_toggle, num_waypoints="default"
):
    """
    Computes the toggle position where the hand meets the object using absolute coordinates.

    Args:
        robot: the robot object 로봇 객체
        toggle_obj: the object to interact with 물체 객체
        relevant_joint: the prismatic joint to interact with 조인트 객체
        num_waypoints: the number of waypoints to interpolate between the start and end poses (default is "default") 시작점 끝점 사이 경로점 개수 (기본값은 "default")

    Returns:
        Tuple, containing:
        offset_grasp_pose_in_world_frame: the position where the hand meets the object
        waypoints: the interpolated waypoints between the start and end poses
        approach_direction_in_world_frame: the approach direction in the world frame
        required_pos_change: the required change in position of the joint to meet the object
    """
    toggle_pose = toggle_obj.get_position_orientation()
    toggle_position, toggle_orientation = toggle_pose
    toggle_orientation = toggle_orientation[[1, 2, 3, 0]]  # [x, y, z, w]로 순서 변경
    """
    # 조인트의 회전 정보를 이용해 밀어야 할 방향을 구합니다
    # 오류나면 이부분 체크
    joint_orientation = lazy.omni.isaac.core.utils.rotations.gf_quat_to_np_array(
        relevant_joint.get_attribute("physics:localRot0")
    )[[1, 2, 3, 0]]
    push_axis = T.quat_apply(
        th.tensor(joint_orientation), th.tensor([1, 0, 0], dtype=th.float32)
    )

    # 물체와 손이 만나는 위치를 절대 좌표로 계산 (밀어야 하는 방향으로 적당한 거리)
    distance_to_object = 0.1  # 예시로, 물체와 손의 만나는 거리 설정
    toggle_position = toggle_position + push_axis * distance_to_object
    """
    # 이 값 그냥 -toggle_orientation으로 바꿔도 될듯_return값이라서 안 됨.
    # 접근 방향을 설정 (예시로 z축 방향)
    approach_direction_in_world_frame = th.tensor([0, 0, -1], dtype=th.float32)

    # 경로 시작 오프셋
    # approach_direction_in_world_frame 대신 -toggle_orientation 사용해도 되지 않나?
    waypoint_start_offset = 0.05 * approach_direction_in_world_frame
    waypoint_start_pose = toggle_position + waypoint_start_offset
    waypoint_end_pose = toggle_position

    # 손이 목표 위치에 닿는 절대 좌표
    offset_grasp_pose_in_world_frame = toggle_position

    # 조인트의 목표 위치 (open/close가 아니라 단순히 목표 위치로 이동)
    toggle_joint_pos = (
        relevant_joint.upper_limit
    )  # 여기서는 upper_limit을 사용한다고 가정
    current_joint_pos = relevant_joint.get_state()[0][0]
    required_pos_change = toggle_joint_pos - current_joint_pos

    # 경로 계산: 시작점과 끝점 사이의 waypoint를 생성
    waypoints = interpolate_waypoints_toggle(
        waypoint_start_pose, waypoint_end_pose, num_waypoints=num_waypoints
    )

    grasp_reguired = True  # 이거 뭘로 반영되는지 체크하고 값 입력해주기. 엥 그리고 왜 색 안 들어옴...?

    return (
        offset_grasp_pose_in_world_frame,
        waypoints,
        approach_direction_in_world_frame,
        False,  # 이거 뭘로 반영되는지 체크하고 값 입력해주기.
        required_pos_change,
    )


def get_toggle_position(
    robot, target_obj, should_toggle, relevant_joint=None, num_waypoints="default"
):
    print("print : target_obj", target_obj)
    print("print : metadata 속성 = ", target_obj.metadata)
    print("print joint에 내용이 있는지 ", target_obj.joints)
    # Pick a moving link of the object.
    # def _get_relevant_joints(obj): 자세히 안 읽어봄
    if relevant_joint is not None:
        relevant_joints = [relevant_joint]
        print("print : 여기감 1")
    else:
        relevant_joints = _get_relevant_joints(target_obj)[1]
        print("print : 여기감 2")
    print("print : relevant_joints = ", relevant_joints)

    if len(relevant_joints) == 0:
        raise ValueError("Cannot toggle object without relevant joints.")

    # Shuffle the indices of relevant joints
    indices = th.randperm(len(relevant_joints))

    # Reorder the joints using the indices
    relevant_joints = [relevant_joints[i] for i in indices]
    selected_joint = None

    for joint in relevant_joints:
        current_position = joint.get_state()[0][0]
        joint_range = joint.upper_limit - joint.lower_limit
        toggle_fraction = (current_position - joint.lower_limit) / joint_range

        if (should_toggle and toggle_fraction < m.TOGGLE_THRESHOLD_TO_TOGGLE) or (
            not should_toggle and toggle_fraction > m.TOGGLE_THRESHOLD_TO_UNTOGGLE
        ):
            selected_joint = joint
            break

    if selected_joint is None:
        return None

    if selected_joint.joint_type == JointType.JOINT_PRISMATIC:
        return (selected_joint,) + toggle_position_for_toggle_on_prismatic_joint(
            robot,
            target_obj,
            selected_joint,
            should_toggle,
            num_waypoints=num_waypoints,
        )
    else:
        raise ValueError(
            "Unknown joint type encountered while generating joint position."
        )
