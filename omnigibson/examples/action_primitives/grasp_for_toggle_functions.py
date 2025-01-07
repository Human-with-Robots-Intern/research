import torch as th
import math
import omnigibson.utils.transform_utils as T


def get_grasp_poses_for_object_sticky_for_toggle(target_obj):
    """
    Obtain a grasp pose for an object from top down, to be used with sticky grasping.

    Args:
        target_object (StatefulObject): Object to get a grasp pose for

    Returns:
        List of grasp candidates, where each grasp candidate is a tuple containing the grasp pose and the approach direction.
    """
    bbox_center_in_world, bbox_quat_in_world, bbox_extent_in_base_frame, _ = (
        target_obj.get_base_aligned_bbox(visual=False)
    )

    grasp_center_pos = bbox_center_in_world + th.tensor(
        [0, 0, th.max(bbox_extent_in_base_frame) + 0.05]
    )
    towards_object_in_world_frame = bbox_center_in_world - grasp_center_pos
    towards_object_in_world_frame /= th.norm(towards_object_in_world_frame)

    grasp_quat = T.euler2quat(th.tensor([0, math.pi / 2, 0], dtype=th.float32))

    grasp_pose = (grasp_center_pos, grasp_quat)
    grasp_candidate = [(grasp_pose, towards_object_in_world_frame)]

    return grasp_candidate
