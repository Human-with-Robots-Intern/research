
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path.cwd()))

from src.utils.task.task_util import TaskUtil
from src.utils.config import constants

# 1. Mock Data: Instruction with a Critical Object but Urgency=False
mock_instruction = [
    {
        "Task": "Boil Water",
        "Subtasks": [
            {
                "Name": "Fill Pot",
                "Type": "Interaction",
                "Repetition": 1,
                "Executions": {
                    "Objects": {"Pot|1": 1, "Faucet|1": 1},
                    "PrimitiveActions": ["NAVIGATE_TO Faucet|1", "TOGGLE_ON Faucet|1"]
                },
                "Duration": {"Type": "Controllable", "Interval": 5},
                "TemporalConstraints": []
            },
            {
                "Name": "Turn Off Faucet",
                "Type": "Interaction",
                "Repetition": 1,
                "Executions": {
                    "Objects": {"Faucet|1": 1},
                    "PrimitiveActions": ["TOGGLE_OFF Faucet|1"]
                },
                "Duration": {"Type": "Controllable", "Interval": 1},
                "TemporalConstraints": [
                    {
                        "Type": "After",
                        "Subtask": "Fill Pot",
                        "Interval": 10,
                        "Urgency": False  # <--- INTENTIONALLY FALSE
                    }
                ]
            }
        ]
    }
]

# 2. Mock Constants/Files (We just need it to run without error)
# TaskUtil checks object IDs, we need to mock that or ensure it passes.
# We can mock _load_object_ids and refine_primitive_actions to do nothing or pass.

# Monkey patch TaskUtil helpers to avoid file I/O dependency
TaskUtil._load_object_ids = lambda scene: {"Combined": ["Faucet|1", "Pot|1"]}
TaskUtil.check_obj_id = lambda scene, tasks: tasks # Skip check
# We need refine_primitive_actions to work or skip. It parses actions. 
# It should differ nav_to logic but our actions are simple.
# Let's let it run or patch it if it fails.

# 3. Process
try:
    print("Running TaskUtil.build_tasks_and_constraints...")
    subtasks, task_graph, bayesian_load = TaskUtil.build_tasks_and_constraints(
        task_data=mock_instruction,
        scene_file_name="FloorPlan1_physics.json",
        enable_decomposition=False 
    )

    # 4. Verification
    print("\nChecking TaskGraph Edges...")
    found_edge = False
    for u, v, data in task_graph.edges(data=True):
        print(f"Edge {u} -> {v}: {data}")
        info = data.get("info", {})
        if info.get("Type") == "After":
            found_edge = True
            is_critical = info.get("IsCritical")
            print(f"\n[Result] 'IsCritical' in Graph: {is_critical}")
            
            if is_critical is True:
                print("SUCCESS: Graph reflects the enforced critical constraint.")
            else:
                print("FAILURE: Graph still shows False.")

    if not found_edge:
        print("FAILURE: Could not find the edge in the graph.")

except Exception as e:
    import traceback
    traceback.print_exc()
