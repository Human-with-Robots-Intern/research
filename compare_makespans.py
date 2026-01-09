import glob
import json
import os

# Base path
base_path = "assets/results/states100/tasks_2_constraints_2"

# Target methods
method_a = "dag_bayesian_NONE_MONITORING"
method_b = "dag_edf"

results = []

# Walk through the directory structure
# Pattern: base_path / <Task> / <FloorPlan> / <Method> / evaluation_result.json

# Get all task directories
task_dirs = [
    d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))
]

for task in task_dirs:
    task_path = os.path.join(base_path, task)
    floorplans = [
        d for d in os.listdir(task_path) if os.path.isdir(os.path.join(task_path, d))
    ]

    for fp in floorplans:
        fp_path = os.path.join(task_path, fp)

        file_a = os.path.join(fp_path, method_a, "evaluation_result.json")
        file_b = os.path.join(fp_path, method_b, "evaluation_result.json")

        if os.path.exists(file_a) and os.path.exists(file_b):
            try:
                with open(file_a, "r") as f:
                    data_a = json.load(f)
                    val_a = data_a.get("makespan", 0)

                with open(file_b, "r") as f:
                    data_b = json.load(f)
                    val_b = data_b.get("makespan", 0)

                # We want cases where A > B (Method A takes longer)
                if val_a > val_b:
                    diff = val_a - val_b
                    results.append(
                        {
                            "task": task,
                            "floorplan": fp,
                            "val_a": val_a,
                            "val_b": val_b,
                            "diff": diff,
                        }
                    )
            except Exception as e:
                print(f"Error reading {fp_path}: {e}")

# Sort by difference descending
results.sort(key=lambda x: x["diff"], reverse=True)

print(f"Total comparisons found where {method_a} > {method_b}: {len(results)}\n")
print(
    f"{'Difference':<12} | {'Makespan A':<12} | {'Makespan B':<12} | {'Task':<50} | {'FloorPlan'}"
)
print("-" * 110)

for res in results:
    # Print mainly significant differences, but listing all for the user to decide the threshold
    print(
        f"{res['diff']:<12.2f} | {res['val_a']:<12.2f} | {res['val_b']:<12.2f} | {res['task']:<50} | {res['floorplan']}"
    )
