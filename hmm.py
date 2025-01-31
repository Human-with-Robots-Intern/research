from typing import List

from core.task import Subtask, Task, TaskGraphBuilder

import json
import requests

API_URL = (
    "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
)
api_token = "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"
headers = {"Authorization": f"Bearer {api_token}"}

def query(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()
tasks = [
    {
        "Task": "Wash dish, egg, and potato.",
        "Subtasks": [
            {
                "Name": "Wash Plate",
                "Repetition": 2,
                "Type": "Interaction",
                "Executions": {
                    "Objects": {"Plate": 1},
                    "PrimitiveActions": [
                        "NAVIGATE_TO Dish",
                        "GRASP Dish",
                        "NAVIGATE_TO Faucet",
                        "TOGGLE_ON Faucet",
                        "PLACE_INSIDE Faucet",
                        "TOGGLE_OFF Faucet",
                        "PLACE_ON_TOP CounterTop",
                    ],
                },
                "Duration": {"Type": "Controllable", "Interval": 4},
                "TemporalConstraints": [],
            },
            {
                "Name": "Wash Egg",
                "Repetition": 1,
                "Type": "Interaction",
                "Executions": {
                    "Objects": {"Egg": 1},
                    "PrimitiveActions": [
                        "NAVIGATE_TO Egg",
                        "GRASP Egg",
                        "NAVIGATE_TO Faucet",
                        "TOGGLE_ON Faucet",
                        "PLACE_INSIDE SinkBasin",
                        "TOGGLE_OFF Faucet",
                        "PLACE_ON_TOP CounterTop",
                    ],
                },
                "Duration": {"Type": "Controllable", "Interval": 2},
                "TemporalConstraints": [],
            },
            {
                "Name": "Wash Potato",
                "Repetition": 1,
                "Type": "Interaction",
                "Executions": {
                    "Objects": {"Potato": 1},
                    "PrimitiveActions": [
                        "NAVIGATE_TO Potato",
                        "GRASP Potato",
                        "NAVIGATE_TO Faucet",
                        "TOGGLE_ON Faucet",
                        "PLACE_INSIDE SinkBasin",
                        "TOGGLE_OFF Faucet",
                        "PLACE_ON_TOP CounterTop",
                    ],
                },
                "Duration": {"Type": "Controllable", "Interval": 2},
                "TemporalConstraints": [],
            },
        ],
    },
    {
        "Task": "Cook egg fry",
        "Subtasks": [
            {
                "Name": "Prepare Egg Fry",
                "Repetition": 1,
                "Type": "Interaction",
                "Executions": {
                    "Objects": {"Egg": 1, "Pan": 1},
                    "PrimitiveActions": [
                        "NAVIGATE_TO Pan",
                        "GRASP Pan",
                        "PLACE_ON_TOP StoveBurner",
                        "NAVIGATE_TO StoveKnob",
                        "TOGGLE_ON StoveBurner",
                        "NAVIGATE_TO Egg",
                        "GRASP Egg",
                        "PLACE_ON_TOP Pan",
                    ],
                },
                "Duration": {"Type": "Controllable", "Interval": 10},
                "TemporalConstraints": [
                    {
                        "Type": "After",
                        "Subtask": "Wash Egg",
                        "Interval": 5,
                        "Urgency": True,
                    }
                ],
            },
            {
                "Name": "Turn off stove after cooking",
                "Repetition": 1,
                "Type": "Interaction",
                "Executions": {
                    "Objects": {"StoveKnob": 1},
                    "PrimitiveActions": [
                        "NAVIGATE_TO StoveKnob",
                        "TOGGLE_OFF StoveKnob",
                    ],
                },
                "Duration": {"Type": "Controllable", "Interval": 0},
                "TemporalConstraints": [
                    {
                        "Type": "After",
                        "Subtask": "Prepare Egg Fry",
                        "Interval": 10,
                        "Urgency": True,
                    }
                ],
            },
        ],
    },
]
objectIds = {
    "OPEN": [
        "Microwave|-00.24|+01.69|-02.53",
        "Fridge|-02.10|+00.00|+01.07",
        "Book|+00.15|+01.10|+00.62",
        "Drawer|-01.56|+00.66|-00.20",
        "Drawer|+00.95|+00.83|-02.20",
        "Drawer|+00.95|+00.56|-02.20",
        "Drawer|-01.56|+00.84|+00.20",
        "Drawer|+00.95|+00.22|-02.20",
        "Drawer|+00.95|+00.71|-02.20",
        "Drawer|+00.95|+00.39|-02.20",
        "Drawer|-01.56|+00.33|-00.20",
        "Drawer|-01.56|+00.84|-00.20",
        "Cabinet|+00.68|+00.50|-02.20",
        "Cabinet|-01.18|+00.50|-02.20",
        "Cabinet|-01.55|+00.50|+00.38",
        "Cabinet|+00.72|+02.02|-02.46",
        "Cabinet|-01.85|+02.02|+00.38",
        "Cabinet|+00.68|+02.02|-02.46",
        "Cabinet|-01.55|+00.50|-01.97",
        "Cabinet|-01.69|+02.02|-02.46",
        "Cabinet|-00.73|+02.02|-02.46",
        "Kettle|+01.04|+00.90|-02.60",
    ],
    "CLOSE": [
        "Microwave|-00.24|+01.69|-02.53",
        "Fridge|-02.10|+00.00|+01.07",
        "Book|+00.15|+01.10|+00.62",
        "Drawer|-01.56|+00.66|-00.20",
        "Drawer|+00.95|+00.83|-02.20",
        "Drawer|+00.95|+00.56|-02.20",
        "Drawer|-01.56|+00.84|+00.20",
        "Drawer|+00.95|+00.22|-02.20",
        "Drawer|+00.95|+00.71|-02.20",
        "Drawer|+00.95|+00.39|-02.20",
        "Drawer|-01.56|+00.33|-00.20",
        "Drawer|-01.56|+00.84|-00.20",
        "Cabinet|+00.68|+00.50|-02.20",
        "Cabinet|-01.18|+00.50|-02.20",
        "Cabinet|-01.55|+00.50|+00.38",
        "Cabinet|+00.72|+02.02|-02.46",
        "Cabinet|-01.85|+02.02|+00.38",
        "Cabinet|+00.68|+02.02|-02.46",
        "Cabinet|-01.55|+00.50|-01.97",
        "Cabinet|-01.69|+02.02|-02.46",
        "Cabinet|-00.73|+02.02|-02.46",
        "Kettle|+01.04|+00.90|-02.60",
    ],
    "TOGGLE_ON": [
        "LightSwitch|+02.33|+01.31|-00.16",
        "StoveKnob|-00.48|+00.88|-02.19",
        "StoveKnob|-00.02|+00.88|-02.19",
        "StoveKnob|-00.33|+00.88|-02.19",
        "StoveKnob|-00.18|+00.88|-02.19",
        "Microwave|-00.24|+01.69|-02.53",
        "Toaster|-01.84|+00.90|+00.13",
        "CoffeeMachine|-01.98|+00.90|-00.19",
        "Faucet|-02.15|+00.91|-01.50",
    ],
    "TOGGLE_OFF": [
        "LightSwitch|+02.33|+01.31|-00.16",
        "StoveKnob|-00.48|+00.88|-02.19",
        "StoveKnob|-00.02|+00.88|-02.19",
        "StoveKnob|-00.33|+00.88|-02.19",
        "StoveKnob|-00.18|+00.88|-02.19",
        "Microwave|-00.24|+01.69|-02.53",
        "Toaster|-01.84|+00.90|+00.13",
        "CoffeeMachine|-01.98|+00.90|-00.19",
        "Faucet|-02.15|+00.91|-01.50",
    ],
    "GRASP": [
        "Vase|+01.56|+00.56|-02.50",
        "Vase|+01.99|+00.56|-02.49",
        "Pan|+00.72|+00.90|-02.42",
        "Cup|+00.37|+01.64|-02.58",
        "PepperShaker|+00.30|+00.90|-02.47",
        "Potato|-01.66|+00.93|-02.15",
        "Bread|-00.52|+01.17|-00.03",
        "CreditCard|-00.46|+01.10|+00.87",
        "Statue|+01.96|+00.18|-02.54",
        "Plate|+00.96|+01.65|-02.61",
        "DishSponge|-01.94|+00.75|-01.71",
        "Spatula|+00.38|+00.91|-02.33",
        "Knife|-01.70|+00.79|-00.22",
        "Bottle|+01.54|+00.89|-02.54",
        "Tomato|-00.39|+01.14|-00.81",
        "Kettle|+01.04|+00.90|-02.60",
        "Mug|-01.76|+00.90|-00.62",
        "WineBottle|-01.00|+01.65|-02.58",
        "Lettuce|-01.81|+00.97|-00.94",
        "Apple|-00.47|+01.15|+00.48",
        "Bowl|+00.27|+01.10|-00.75",
        "Spoon|+00.98|+00.77|-02.29",
        "Egg|-02.04|+00.81|+01.24",
        "Fork|+00.95|+00.77|-02.37",
        "PaperTowelRoll|-02.06|+01.01|-00.81",
        "SaltShaker|+00.35|+00.90|-02.57",
        "SoapBottle|-01.99|+00.90|-02.03",
        "Pot|-01.22|+00.90|-02.36",
        "ButterKnife|-00.41|+01.11|-00.46",
        "Book|+00.15|+01.10|+00.62",
    ],
    "SLICE": [
        "Tomato|-00.39|+01.14|-00.81",
        "Apple|-00.47|+01.15|+00.48",
        "Potato|-01.66|+00.93|-02.15",
        "Bread|-00.52|+01.17|-00.03",
        "Lettuce|-01.81|+00.97|-00.94",
        "Egg|-02.04|+00.81|+01.24",
    ],
    "RECEPTACLE": [
        "Pan|+00.72|+00.90|-02.42",
        "Cup|+00.37|+01.64|-02.58",
        "GarbageCan|-01.94|00.00|+02.03",
        "Shelf|+01.75|+00.17|-02.56",
        "Shelf|+01.75|+00.88|-02.56",
        "Shelf|+01.75|+00.55|-02.56",
        "Stool|+00.70|+00.00|-00.51",
        "Stool|+00.74|+00.00|+00.56",
        "Plate|+00.96|+01.65|-02.61",
        "Cabinet|+00.68|+00.50|-02.20",
        "Cabinet|-01.18|+00.50|-02.20",
        "Cabinet|-01.55|+00.50|+00.38",
        "Cabinet|+00.72|+02.02|-02.46",
        "Cabinet|-01.85|+02.02|+00.38",
        "Cabinet|+00.68|+02.02|-02.46",
        "Cabinet|-01.55|+00.50|-01.97",
        "Cabinet|-01.69|+02.02|-02.46",
        "Cabinet|-00.73|+02.02|-02.46",
        "Mug|-01.76|+00.90|-00.62",
        "Microwave|-00.24|+01.69|-02.53",
        "Sink|-01.90|+00.97|-01.50|SinkBasin",
        "Toaster|-01.84|+00.90|+00.13",
        "Bowl|+00.27|+01.10|-00.75",
        "Drawer|-01.56|+00.66|-00.20",
        "Drawer|+00.95|+00.83|-02.20",
        "Drawer|+00.95|+00.56|-02.20",
        "Drawer|-01.56|+00.84|+00.20",
        "Drawer|+00.95|+00.22|-02.20",
        "Drawer|+00.95|+00.71|-02.20",
        "Drawer|+00.95|+00.39|-02.20",
        "Drawer|-01.56|+00.33|-00.20",
        "Drawer|-01.56|+00.84|-00.20",
        "CounterTop|+00.69|+00.95|-02.48",
        "CounterTop|-00.08|+01.15|00.00",
        "CounterTop|-01.87|+00.95|-01.21",
        "CoffeeMachine|-01.98|+00.90|-00.19",
        "Floor|+00.00|+00.00|+00.00",
        "Fridge|-02.10|+00.00|+01.07",
        "Pot|-01.22|+00.90|-02.36",
        "StoveBurner|-00.47|+00.92|-02.37",
        "StoveBurner|-00.04|+00.92|-02.58",
        "StoveBurner|-00.47|+00.92|-02.58",
        "StoveBurner|-00.04|+00.92|-02.37",
    ],
}


def check_obj_id(tasks):
    all_object_ids = set()
    for key in objectIds:
        all_object_ids.update(objectIds[key])
    for task in tasks:
        for subtask in task["Subtasks"]:
            actions = subtask["Executions"]["PrimitiveActions"]
            for i, action in enumerate(actions):
                step = action.split(" ")[0]  ## action 이름
                to_obj = action.split(" ")[1]  ## object의 이름
                if step == "NAVIGATE_TO":
                    if to_obj not in all_object_ids:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": list(all_object_ids),
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = list(all_object_ids)[idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
                elif step in ["PLACE_INSIDE", "PLACE_ON_TOP"]:
                    if to_obj not in objectIds["RECEPTACLE"]:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": objectIds["RECEPTACLE"],
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = objectIds["RECEPTACLE"][idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
                else:
                    if to_obj not in objectIds[step]:
                        print(f"{to_obj} 안맞음")
                        # 유사도 검사
                        data = query(
                            {
                                "inputs": {
                                    "source_sentence": f"{to_obj}",
                                    "sentences": objectIds[step],
                                }
                            }
                        )
                        # 가장 유사한 object의 index
                        idx = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][
                            0
                        ]
                        real_obj_id = objectIds[step][idx]
                        actions[i] = f"{step} {real_obj_id}"
                        print(actions[i])
    return tasks

check_obj_id(tasks)
