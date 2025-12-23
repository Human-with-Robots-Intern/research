import glob
import json
import os
from pathlib import Path

import pandas as pd

# Base directory
base_dir = "/home/dongkyu/pdk_ws/research/assets/tasks/sampled_10_instruction_set_for_final_experiment_251203"

# List to store data
data_list = []

# Walk through the directory
for root, dirs, files in os.walk(base_dir):
    for file in files:
        if file.endswith(".json"):
            file_path = os.path.join(root, file)

            # Determine category (e.g., tasks_2_constraints_0)
            # Structure: base_dir/category/floorplan/file.json
            rel_path = os.path.relpath(file_path, base_dir)
            parts = rel_path.split(os.sep)

            if len(parts) < 2:
                continue

            category = parts[0]
            floorplan = parts[1]

            try:
                with open(file_path, "r") as f:
                    content = json.load(f)

                # Calculate counts
                num_high_level_tasks = len(content)

                num_subtasks = 0
                num_constraints = 0

                # Counters for specific constraint types
                inv0_urgF = 0
                inv0_urgT = 0
                invNot0_urgF = 0
                invNot0_urgT = 0

                for task in content:
                    subtasks = task.get("Subtasks", [])
                    num_subtasks += len(subtasks)

                    for subtask in subtasks:
                        constraints = subtask.get("TemporalConstraints", [])
                        num_constraints += len(constraints)

                        for constr in constraints:
                            interval = constr.get("Interval", 0)
                            urgency = constr.get("Urgency", False)

                            if interval == 0:
                                if urgency:
                                    inv0_urgT += 1
                                else:
                                    inv0_urgF += 1
                            else:
                                if urgency:
                                    invNot0_urgT += 1
                                else:
                                    invNot0_urgF += 1

                data_list.append(
                    {
                        "Category": category,
                        "FloorPlan": floorplan,
                        "File": file,
                        "Num_HighLevel_Tasks": num_high_level_tasks,
                        "Num_Subtasks": num_subtasks,
                        "Num_Constraints": num_constraints,
                        "Inv0_UrgT": inv0_urgT,
                        "Inv0_UrgF": inv0_urgF,
                        "InvNot0_UrgT": invNot0_urgT,
                        "InvNot0_UrgF": invNot0_urgF,
                    }
                )

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

# Create DataFrame
df = pd.DataFrame(data_list)

if df.empty:
    print("No data found.")
else:
    # Group by Category and calculate statistics
    # We are interested in actual subtask counts and constraint counts

    # Sort categories for better readability
    def sort_key(s):
        # Extract numbers for sorting
        try:
            parts = s.split("_")
            t = int(parts[1])
            c = int(parts[3])
            return (t, c)
        except:
            return (0, 0)

    categories = sorted(df["Category"].unique(), key=sort_key)

    print("\n--- Summary Statistics by Category ---")
    print(
        f"{'Category':<25} | {'Avg Tasks':<10} | {'Avg Subtasks':<12} | {'Avg Constraints':<15} | {'Count':<5}"
    )
    print("-" * 80)

    for cat in categories:
        cat_df = df[df["Category"] == cat]
        avg_tasks = cat_df["Num_HighLevel_Tasks"].mean()
        avg_subtasks = cat_df["Num_Subtasks"].mean()
        avg_constraints = cat_df["Num_Constraints"].mean()
        count = len(cat_df)

        print(
            f"{cat:<25} | {avg_tasks:<10.2f} | {avg_subtasks:<12.2f} | {avg_constraints:<15.2f} | {count:<5}"
        )

    print("\n\n--- Detailed Distribution (Min/Max) ---")
    print(
        f"{'Category':<25} | {'Subtasks (Min-Max)':<20} | {'Constraints (Min-Max)':<25}"
    )
    print("-" * 80)
    for cat in categories:
        cat_df = df[df["Category"] == cat]
        min_sub = cat_df["Num_Subtasks"].min()
        max_sub = cat_df["Num_Subtasks"].max()
        min_cons = cat_df["Num_Constraints"].min()
        max_cons = cat_df["Num_Constraints"].max()

        print(f"{cat:<25} | {min_sub}-{max_sub:<18} | {min_cons}-{max_cons:<23}")

    print("\n\n--- Detailed Temporal Constraint Breakdown (Average per File) ---")
    print(
        f"{'Category':<25} | {'Inv=0, Urg=T':<14} | {'Inv=0, Urg=F':<14} | {'Inv!=0, Urg=T':<15} | {'Inv!=0, Urg=F':<15}"
    )
    print("-" * 90)

    for cat in categories:
        cat_df = df[df["Category"] == cat]
        avg_i0_ut = cat_df["Inv0_UrgT"].mean()
        avg_i0_uf = cat_df["Inv0_UrgF"].mean()
        avg_in0_ut = cat_df["InvNot0_UrgT"].mean()
        avg_in0_uf = cat_df["InvNot0_UrgF"].mean()

        print(
            f"{cat:<25} | {avg_i0_ut:<14.2f} | {avg_i0_uf:<14.2f} | {avg_in0_ut:<15.2f} | {avg_in0_uf:<15.2f}"
        )
