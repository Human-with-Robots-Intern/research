import argparse
import os

import yaml

import omnigibson as og
from omnigibson import object_states
from omnigibson.action_primitives.starter_semantic_action_primitives import (
    StarterSemanticActionPrimitives,
    StarterSemanticActionPrimitiveSet,
)
from omnigibson.macros import gm

# Don't use GPU dynamics and use flatcache for performance boost
# gm.USE_GPU_DYNAMICS = True
# gm.ENABLE_FLATCACHE = True


def execute_controller(ctrl_gen, env):
    for action in ctrl_gen:
        env.step(action)


def init_scene():

    # Load the config
    config_filename = os.path.join(og.example_config_path, "fetch_primitives.yaml")
    config = yaml.load(open(config_filename, "r"), Loader=yaml.FullLoader)

    # Update it to run a grocery shopping task
    config["scene"]["scene_model"] = "Rs_int"
    config["scene"]["not_load_object_categories"] = ["ceilings"]
    config["objects"] = [
        {
            "type": "DatasetObject",
            "name": "apple",
            "category": "apple",
            "model": "agveuv",
            "position": [-0.3, -1.1, 0.5],
            "orientation": [0, 0, 0, 1],
        },
        dict(
            type="LightObject",
            light_type="Sphere",
            name="light",
            radius=1,
            intensity=0,
            position=[-0.3, -1.1, 3.0],
        ),
    ]

    # Load the environment
    env = og.Environment(configs=config)
    scene = env.scene
    robot = env.robots[0]
    return env, scene


def main():
    """
    Demonstrates how to use the action primitives to pick and place an object in a crowded scene.

    It loads Rs_int with a robot, and the robot picks and places an apple.
    """

    parser = argparse.ArgumentParser(description="안녕? 액션을 테스팅해보자!")
    parser.add_argument(
        "-c",
        "--case",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help=(
            "Choose a case:\n"
            "  1) pick & place\n"
            "  2) open & close\n"
            "  3) on & off"
        ),
    )
    args = parser.parse_args()  # ArgumentParser 객체의 parse_args 호출로 인수 파싱

    env, scene = init_scene()

    # Allow user to move camera more easily
    og.sim.enable_viewer_camera_teleoperation()

    controller = StarterSemanticActionPrimitives(env, enable_head_tracking=False)

    # match-case 구조
    match args.case:  # 이제 args.case가 정상적으로 참조 가능
        case 1:
            apple = scene.object_registry("name", "apple")
            # Pick and Place
            print("Executing controller: Grasp")
            execute_controller(
                controller.apply_ref(StarterSemanticActionPrimitiveSet.GRASP, apple),
                env,
            )
            print("Finished executing grasp")

            cabinet = scene.object_registry("name", "bottom_cabinet_bamfsz_0")
            print("Executing controller: Place on Top")
            execute_controller(
                controller.apply_ref(
                    StarterSemanticActionPrimitiveSet.PLACE_ON_TOP, cabinet
                ),
                env,
            )
            print("Finished executing place")

        case 2:
            cabinet = scene.object_registry("name", "bottom_cabinet_bamfsz_0")
            # Open Close
            print("Executing controller: Open")
            execute_controller(
                controller.apply_ref(StarterSemanticActionPrimitiveSet.OPEN, cabinet),
                env,
            )
            print("Finished executing open")

            print("Executing controller: Close")
            execute_controller(
                controller.apply_ref(StarterSemanticActionPrimitiveSet.CLOSE, cabinet),
                env,
            )
            print("Finished executing close")

        case 3:
            objs = [
                "electric_switch_wseglt_1",
                "electric_switch_wseglt_2",
                # "floor_lamp_vdxlda_0",
                # "laptop_nvulcs_0",
                # "loudspeaker_bmpdyv_0",
                # "standing_tv_udotid_0",
                # "table_lamp_xbfgjc_0",
            ]

            for obj_name in objs:
                obj = scene.object_registry("name", obj_name)
                # Switch On Off
                print("Executing controller: Toggle On")
                execute_controller(
                    controller.apply_ref(
                        StarterSemanticActionPrimitiveSet.TOGGLE_ON, obj
                    ),
                    env,
                )

                if obj.states[object_states.ToggledOn].get_value() == True:
                    intensity_light = 1e4

                    light = scene.object_registry("name", "light")
                    light._light_link.set_attribute("inputs:intensity", intensity_light)
                    env.step()

                print("Finished executing on")
                """
                print("Executing controller: Toggle Off")
                execute_controller(
                    controller.apply_ref(
                        StarterSemanticActionPrimitiveSet.TOGGLE_OFF, obj
                    ),
                    env,
                )
                if obj.states[object_states.ToggledOn].get_value() == False :
                    intensity_light = 0

                    light = scene.object_registry("name", "light")
                    light._light_link.set_attribute("inputs:intensity", intensity_light)
                
                print("Finished executing off")
                """
        case _:
            print(
                "Invalid case selected. This should not happen due to argparse validation."
            )


if __name__ == "__main__":
    main()
