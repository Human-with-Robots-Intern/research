import re

import numpy as np

log_file = "logs/all_log/20251203_1420.log"

nav_costs = []
urg_costs = []
rem_costs = []
total_costs = []

with open(log_file, "r") as f:
    for line in f:
        # Parse standard heuristic
        if "Heuristic for" in line and "CandNav" in line:
            # Format: CandNav(alpha*val)=cost, Urg(beta*val)=cost (Slack=...), RemWork(gamma*Rem[...])=cost
            try:
                nav_match = re.search(r"CandNav\([^)]+\)=([\d\.]+)", line)
                urg_match = re.search(r"Urg\([^)]+\)=([\d\.]+)", line)
                rem_match = re.search(r"RemWork\([^)]+\)=([\d\.]+)", line)

                if nav_match and urg_match and rem_match:
                    nav_costs.append(float(nav_match.group(1)))
                    urg_costs.append(float(urg_match.group(1)))
                    rem_costs.append(float(rem_match.group(1)))
            except Exception as e:
                print(f"Error parsing line: {line.strip()} - {e}")

        # Parse Wait heuristic
        elif "Heuristic for" in line and "WaitUrgency" in line:
            # Format: WaitUrgency(beta*val)=cost, RemWorkAfterWait(gamma*Rem[...])=cost
            try:
                urg_match = re.search(r"WaitUrgency\([^)]+\)=([\d\.]+)", line)
                rem_match = re.search(r"RemWorkAfterWait\([^)]+\)=([\d\.]+)", line)

                if urg_match and rem_match:
                    # Wait has no Nav cost, so 0
                    nav_costs.append(0.0)
                    urg_costs.append(float(urg_match.group(1)))
                    rem_costs.append(float(rem_match.group(1)))
            except Exception as e:
                print(f"Error parsing wait line: {line.strip()} - {e}")

print(f"Parsed {len(nav_costs)} heuristic entries.")

if nav_costs:
    print("\n--- Heuristic Component Scale Analysis ---")
    print(
        f"Navigation Cost (Weighted): Mean={np.mean(nav_costs):.2f}, Max={np.max(nav_costs):.2f}, Min={np.min(nav_costs):.2f}, Std={np.std(nav_costs):.2f}"
    )
    print(
        f"Urgency Cost (Weighted):    Mean={np.mean(urg_costs):.2f}, Max={np.max(urg_costs):.2f}, Min={np.min(urg_costs):.2f}, Std={np.std(urg_costs):.2f}"
    )
    print(
        f"Remaining Work (Weighted):  Mean={np.mean(rem_costs):.2f}, Max={np.max(rem_costs):.2f}, Min={np.min(rem_costs):.2f}, Std={np.std(rem_costs):.2f}"
    )

    print("\n--- Ratios (based on Means) ---")
    total_mean = np.mean(nav_costs) + np.mean(urg_costs) + np.mean(rem_costs)
    if total_mean > 0:
        print(f"Nav: {np.mean(nav_costs)/total_mean*100:.1f}%")
        print(f"Urg: {np.mean(urg_costs)/total_mean*100:.1f}%")
        print(f"Rem: {np.mean(rem_costs)/total_mean*100:.1f}%")
else:
    print("No heuristic entries found.")
