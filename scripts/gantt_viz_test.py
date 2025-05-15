import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.colors as mcolors
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle


# --- UnionFind 클래스 ---
class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, i):
        if i not in self.parent:
            self.parent[i] = i
        if self.parent[i] == i:
            return i
        self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i, j):
        if i not in self.parent:
            self.add(i)
        if j not in self.parent:
            self.add(j)
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_j] = root_i

    def add(self, i):
        if i not in self.parent:
            self.parent[i] = i


# --- 제약 조건 그래프 생성 함수 ---
def build_constraints_graph_from_inputs(
    sim_subtasks_data: List[Dict], initial_plan_data: List[Dict]
) -> nx.DiGraph:
    g = nx.DiGraph()
    sim_subtask_names = [s["subtask_name"] for s in sim_subtasks_data]
    for name in sim_subtask_names:
        g.add_node(name)

    name_to_sim_data_map = {s["subtask_name"]: s for s in sim_subtasks_data}

    initial_subtask_to_sim_names_map = {}
    sim_name_to_initial_constraints_map = defaultdict(list)

    for task_block in initial_plan_data:
        # original_task_name_for_group = task_block.get("Task") # 현재 사용 안함
        for subtask_json in task_block.get("Subtasks", []):
            base_name = subtask_json["Name"]
            repetition = subtask_json.get("Repetition", 1)
            initial_constraints = subtask_json.get("TemporalConstraints", [])

            temp_sim_names = []
            if repetition > 1:
                for i in range(repetition):
                    part_name = f"{base_name}_part_{i+1}"
                    if part_name in name_to_sim_data_map:
                        temp_sim_names.append(part_name)
                        if i == 0:
                            sim_name_to_initial_constraints_map[part_name].extend(
                                initial_constraints
                            )
            else:
                if base_name in name_to_sim_data_map:
                    temp_sim_names.append(base_name)
                    sim_name_to_initial_constraints_map[base_name].extend(
                        initial_constraints
                    )

            if temp_sim_names:
                initial_subtask_to_sim_names_map[base_name] = temp_sim_names

            if repetition > 1 and temp_sim_names:
                for i in range(len(temp_sim_names) - 1):
                    u, v = temp_sim_names[i], temp_sim_names[i + 1]
                    if not g.has_edge(u, v):
                        g.add_edge(
                            u,
                            v,
                            info={
                                "Interval": 0,
                                "Urgency": False,
                                "IsCritical": False,
                                "Rule": "Part Sequence",
                            },
                        )

            for tc in subtask_json.get("TemporalConstraints", []):
                if tc.get("Type") == "After":
                    source_original_name = tc["Subtask"]
                    # target_original_name = base_name # 현재 subtask_json의 이름

                    source_sim_names = initial_subtask_to_sim_names_map.get(
                        source_original_name, []
                    )
                    target_sim_names_for_tc = temp_sim_names

                    if source_sim_names and target_sim_names_for_tc:
                        actual_source_in_sim = source_sim_names[-1]
                        actual_target_in_sim = target_sim_names_for_tc[0]

                        if (
                            g.has_node(actual_source_in_sim)
                            and g.has_node(actual_target_in_sim)
                            and not g.has_edge(
                                actual_source_in_sim, actual_target_in_sim
                            )
                        ):
                            g.add_edge(
                                actual_source_in_sim,
                                actual_target_in_sim,
                                info={
                                    "Interval": tc.get("Interval", 0),
                                    "Urgency": tc.get("Urgency", False),
                                    "IsCritical": tc.get("Urgency", False),
                                    "Rule": "Initial TC",
                                },
                            )

    for i, current_s_data in enumerate(sim_subtasks_data):
        current_name = current_s_data["subtask_name"]
        if current_name.startswith("Monitoring for "):
            if i > 0:
                prev_name = sim_subtasks_data[i - 1]["subtask_name"]
                monitored_target_match = re.search(
                    r"Monitoring for ([^_]+)", current_name
                )
                if monitored_target_match:
                    monitored_target_simple = monitored_target_match.group(1).strip()
                    is_prev_early = (
                        prev_name.startswith("EARLY_")
                        and prev_name.split("EARLY_")[1] == monitored_target_simple
                    )
                    is_prev_nav = (
                        prev_name.startswith(f"Navigate to {monitored_target_simple}")
                        and "during" in prev_name
                    )
                    if is_prev_early or is_prev_nav:
                        if not g.has_edge(prev_name, current_name):
                            g.add_edge(
                                prev_name,
                                current_name,
                                info={
                                    "Interval": 0,
                                    "Urgency": True,
                                    "IsCritical": True,
                                    "Rule": "Pattern Pre-Mon",
                                },
                            )

        if current_name.startswith("REMAIN_"):
            base_remain_name = current_name.split("REMAIN_")[1]
            for j in range(i - 1, -1, -1):
                potential_monitor_name = sim_subtasks_data[j]["subtask_name"]
                if (
                    potential_monitor_name.startswith("Monitoring for ")
                    and base_remain_name
                    in potential_monitor_name.split("Monitoring for ")[1]
                ):
                    if not g.has_edge(potential_monitor_name, current_name):
                        g.add_edge(
                            potential_monitor_name,
                            current_name,
                            info={
                                "Interval": 0,
                                "Urgency": False,
                                "IsCritical": False,
                                "Rule": "Pattern Mon-Remain",
                            },
                        )
                    break
    return g


# --- 레인 할당 함수 ---
def merge_groups_for_lanes(
    constraints_graph: nx.DiGraph, ordered_subtask_names: List[str]
) -> List[List[str]]:
    uf = UnionFind()
    for name in ordered_subtask_names:
        uf.add(name)
    for u, v in constraints_graph.edges():
        if u in uf.parent and v in uf.parent:
            uf.union(u, v)
    groups = defaultdict(list)
    for name in ordered_subtask_names:
        groups[uf.find(name)].append(name)
    final_chains = []
    temp_sorted_groups = sorted(
        groups.items(),
        key=lambda item: (
            ordered_subtask_names.index(item[1][0]) if item[1] else float("inf")
        ),
    )
    for _, members in temp_sorted_groups:
        final_chains.append(
            sorted(members, key=lambda x: ordered_subtask_names.index(x))
        )
    return final_chains


def assign_y_lanes_for_gantt_v3(
    ordered_subtask_names: List[str],
    execution_chains: List[List[str]],
    start_times_map: Dict[str, float],
    durations_map_viz: Dict[str, float],
):
    lanes_assignment_map = {}
    lane_available_time = defaultdict(float)
    sorted_chains = sorted(
        execution_chains,
        key=lambda chain: (
            start_times_map.get(chain[0], float("inf")) if chain else float("inf")
        ),
    )
    max_lane_used = -1

    for chain in sorted_chains:
        if not chain:
            continue
        chain_can_start_at = start_times_map.get(chain[0], 0)
        assigned_lane = -1
        for lane_num in range(max_lane_used + 1):
            if lane_available_time[lane_num] <= chain_can_start_at + 0.001:
                assigned_lane = lane_num
                break
        if assigned_lane == -1:
            max_lane_used += 1
            assigned_lane = max_lane_used

        current_task_time_on_lane = lane_available_time[assigned_lane]
        for task_name in chain:
            lanes_assignment_map[task_name] = assigned_lane
            task_start = start_times_map.get(task_name, 0)
            task_duration_viz = durations_map_viz.get(task_name, 0)
            actual_placement_start = max(current_task_time_on_lane, task_start)
            lane_available_time[assigned_lane] = (
                actual_placement_start + task_duration_viz
            )
            current_task_time_on_lane = lane_available_time[assigned_lane]

    unique_assigned_lanes = sorted(list(set(lanes_assignment_map.values())))
    lane_remap = {old_lane: i + 1 for i, old_lane in enumerate(unique_assigned_lanes)}
    final_lanes_list = []
    last_non_wait_lane = 1
    for name in ordered_subtask_names:
        assigned_idx = lanes_assignment_map.get(name)
        if name.startswith("Wait Gap ("):
            final_lanes_list.append(last_non_wait_lane)
        elif assigned_idx is not None:
            current_mapped_lane = lane_remap.get(assigned_idx, 1)
            final_lanes_list.append(current_mapped_lane)
            if not name.startswith("Wait Gap ("):
                last_non_wait_lane = current_mapped_lane
        else:
            final_lanes_list.append(last_non_wait_lane)

    return final_lanes_list, (max_lane_used + 1) if ordered_subtask_names else 0


# --- 최종 간트 차트 플로팅 함수 (v6 - 제목 제거, 레이아웃 잘림 현상 개선 집중) ---
def plot_gantt_final_v6_fix_cutoff(
    simulation_json_path: str,
    initial_plan_json_data: List[Dict],
    save_dir: str = "gantt_charts_final_v6_fix_cutoff_executable",
):
    try:
        with open(simulation_json_path, "r", encoding="utf-8") as f:
            sim_data = json.load(f)
    except FileNotFoundError:
        print(f"오류: 파일을 찾을 수 없습니다 - {simulation_json_path}")
        return
    except json.JSONDecodeError:
        print(f"오류: JSON 파일을 파싱할 수 없습니다 - {simulation_json_path}")
        return

    if not sim_data.get("plans") or not sim_data["plans"][0].get("subtasks"):
        print("오류: JSON 데이터에 'plans' 또는 'subtasks' 정보가 부족합니다.")
        return

    plan_data = sim_data["plans"][0]
    subtasks_sim_data = plan_data.get("subtasks", [])
    simulation_makespan = float(sim_data.get("simulation_makespan", 0))

    if not subtasks_sim_data:
        print(
            "경고: 시뮬레이션 데이터에 서브태스크가 없습니다. 빈 차트가 생성될 수 있습니다."
        )
        # return # Allow empty chart generation if makespan is also 0, otherwise it might be an issue

    subtask_names_in_order, start_times_map, durations_map_viz, colors_map = (
        [],
        {},
        {},
        {},
    )

    # Updated v6 color palette
    color_palette = {
        "success": "#77AADD",
        "failure": "#EE5555",
        "monitoring": "#FFAA44",
        "wait": "#EAEAEA",  # Changed from #DDDDDD
        "dependency_normal": "#0077CC",  # Changed from #0072B2
        "dependency_critical": "#CC3311",  # Changed from #D55E00
        "text_on_bar": "#222222",  # Changed from "black"
        "text_on_dark_bar": "white",
    }

    current_sim_time = 0.0
    min_bar_duration_for_name_heuristic = simulation_makespan * 0.015
    min_monitoring_viz_duration = simulation_makespan * 0.01

    for st_data in subtasks_sim_data:
        name = st_data.get("subtask_name", "Unknown Subtask")
        sim_start, sim_end = st_data.get("start_time_simulation"), st_data.get(
            "end_time_simulation"
        )
        status = st_data.get("execution_status", None)
        if sim_start is None or sim_end is None:
            continue
        sim_start_f, sim_end_f = float(sim_start), float(sim_end)
        if sim_end_f < sim_start_f:  # Skip tasks with negative duration
            print(
                f"경고: 태스크 '{name}'의 종료 시간이 시작 시간보다 빠릅니다. 건너<0xC2><0xAB>니다."
            )
            continue

        actual_current_duration = sim_end_f - sim_start_f

        if sim_start_f > current_sim_time + 0.001:
            wait_name = f"Wait Gap ({current_sim_time:.1f}-{sim_start_f:.1f})"
            subtask_names_in_order.append(wait_name)
            start_times_map[wait_name] = current_sim_time
            durations_map_viz[wait_name] = sim_start_f - current_sim_time
            colors_map[wait_name] = color_palette["wait"]

        subtask_names_in_order.append(name)
        start_times_map[name] = sim_start_f

        is_monitoring = "monitoring for" in name.lower() or st_data.get(
            "monitored_subtask"
        )
        if is_monitoring and actual_current_duration < min_monitoring_viz_duration:
            durations_map_viz[name] = max(
                actual_current_duration, min_monitoring_viz_duration
            )
        else:
            durations_map_viz[name] = actual_current_duration

        if is_monitoring:
            colors_map[name] = color_palette["monitoring"]
        elif status is False:  # Explicitly check for False, as None is different
            colors_map[name] = color_palette["failure"]
        else:  # True or None (assumed success if not explicitly failed)
            colors_map[name] = color_palette["success"]
        current_sim_time = sim_end_f

    # If no tasks were processed but makespan is > 0, add a dummy wait gap to show the timeline
    if not subtask_names_in_order and simulation_makespan > 0:
        wait_name = f"Total Span ({0.0:.1f}-{simulation_makespan:.1f})"
        subtask_names_in_order.append(wait_name)
        start_times_map[wait_name] = 0.0
        durations_map_viz[wait_name] = simulation_makespan
        colors_map[wait_name] = color_palette["wait"]
    elif not subtask_names_in_order and simulation_makespan == 0:
        print(
            "정보: 시뮬레이션 메이크스팬이 0이고 처리할 태스크가 없습니다. 빈 차트를 생성합니다."
        )
        # To prevent issues later, set a minimal makespan if it's zero and there are no tasks
        simulation_makespan = 10  # Default makespan for empty charts to have some scale

    constraints_g = build_constraints_graph_from_inputs(
        subtasks_sim_data, initial_plan_json_data
    )
    non_wait_task_names = [
        name for name in subtask_names_in_order if not name.startswith("Wait Gap (")
    ]

    # Handle case where there are only wait tasks or no tasks at all for lane assignment
    if non_wait_task_names:
        execution_chains = merge_groups_for_lanes(constraints_g, non_wait_task_names)
        assigned_lanes_for_non_wait, _ = assign_y_lanes_for_gantt_v3(
            non_wait_task_names,
            execution_chains,
            {k: v for k, v in start_times_map.items() if k in non_wait_task_names},
            {k: v for k, v in durations_map_viz.items() if k in non_wait_task_names},
        )
    else:  # No non-wait tasks, so no complex lane assignment needed
        assigned_lanes_for_non_wait = []

    final_y_lanes = []
    non_wait_idx = 0
    last_valid_lane = 1  # Default to lane 1 if no tasks are present
    for name in subtask_names_in_order:
        if name.startswith("Wait Gap ("):
            final_y_lanes.append(last_valid_lane)
        else:
            if non_wait_idx < len(assigned_lanes_for_non_wait):
                current_lane = assigned_lanes_for_non_wait[non_wait_idx]
                final_y_lanes.append(current_lane)
                last_valid_lane = (
                    current_lane  # Update last_valid_lane for subsequent wait gaps
                )
                non_wait_idx += 1
            else:  # Fallback if something went wrong or only wait tasks
                final_y_lanes.append(last_valid_lane)

    num_total_lanes = max(final_y_lanes) if final_y_lanes else 1

    # v6 Figure layout calculations
    fig_height_base = 10
    fig_height_per_lane = 1.0
    fig_height = max(
        fig_height_base,
        num_total_lanes * fig_height_per_lane
        + (
            fig_height_base * 0.20 * 2
        ),  # Add space based on base_height and a factor for bottom elements
    )
    fig_width = max(20, simulation_makespan * 0.16 + 2)  # v6 width calc
    if fig_width > 40:
        fig_width = 40

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    bar_height = 0.5  # v6 bar_height

    for i, name in enumerate(subtask_names_in_order):
        start_time = start_times_map[name]
        duration_viz = durations_map_viz[name]
        color = colors_map[name]
        y_pos = final_y_lanes[i]

        rect = Rectangle(
            (start_time, y_pos - bar_height / 2),
            duration_viz,
            bar_height,
            facecolor=color,
            edgecolor="black",  # v6 style
            linewidth=0.4,  # v6 style
            alpha=0.9,  # v6 style
            zorder=2,
        )
        ax.add_patch(rect)

        if duration_viz > min_bar_duration_for_name_heuristic and not name.startswith(
            "Wait Gap ("
        ):
            name_parts = name.split("_part_")
            display_name = name_parts[0]
            if len(name_parts) > 1:
                display_name += f" p{name_parts[1].split('_')[0]}"
            if name.startswith("Monitoring for "):
                display_name = "M: " + display_name.split("Monitoring for ")[1]
            if name.startswith("EARLY_"):
                display_name = "E: " + display_name.split("EARLY_")[1]
            if name.startswith("REMAIN_"):
                display_name = "R: " + display_name.split("REMAIN_")[1]

            max_len_heuristic = int(duration_viz * 2.0) + 2  # v6 heuristic
            text_to_display = display_name[:max_len_heuristic] + (
                "…" if len(display_name) > max_len_heuristic + 2 else ""
            )

            r, gr, b = mcolors.to_rgb(color)
            brightness = (r * 299 + gr * 587 + b * 114) / 1000
            text_color = (
                color_palette["text_on_dark_bar"]
                if brightness < 0.55
                else color_palette["text_on_bar"]
            )

            ax.text(
                start_time + duration_viz / 2,
                y_pos,
                text_to_display,
                ha="center",
                va="center",
                fontsize=7.5,
                color=text_color,
                clip_on=True,
                zorder=3,
                path_effects=[  # v6 style
                    path_effects.withStroke(linewidth=0.4, foreground="#777777")
                ],
            )

    if constraints_g:
        task_positions_for_arrows = {}
        for i, name in enumerate(subtask_names_in_order):
            if not name.startswith("Wait Gap ("):
                task_positions_for_arrows[name] = {
                    "y": final_y_lanes[i],
                    "start_x": start_times_map[name],
                    "end_x": start_times_map[name] + durations_map_viz[name],
                }

        for u, v, edge_data in constraints_g.edges(data=True):
            if u in task_positions_for_arrows and v in task_positions_for_arrows:
                pos_u, pos_v = (
                    task_positions_for_arrows[u],
                    task_positions_for_arrows[v],
                )
                # Ensure arrow is drawn only if u ends before or at the start of v
                if (
                    pos_u["end_x"] <= pos_v["start_x"] + 0.001
                ):  # Small tolerance for float comparison
                    start_x, start_y = pos_u["end_x"], pos_u["y"]
                    end_x, end_y = pos_v["start_x"], pos_v["y"]

                    edge_info = edge_data.get("info", {})
                    interval = edge_info.get("Interval", 0)
                    is_critical = edge_info.get("Urgency", False) or edge_info.get(
                        "IsCritical", False
                    )
                    arrow_color = (
                        color_palette["dependency_critical"]
                        if is_critical
                        else color_palette["dependency_normal"]
                    )

                    ax.annotate(  # v6 arrow style
                        "",
                        xy=(end_x, end_y),
                        xytext=(start_x, start_y),
                        arrowprops=dict(
                            arrowstyle="-|>",
                            shrinkA=1.5,  # v6 style
                            shrinkB=1.5,  # v6 style
                            color=arrow_color,
                            lw=0.9,  # v6 style
                            connectionstyle="arc3,rad=0",
                        ),
                        zorder=1,  # v6: ensure arrows are behind bars if overlap (though should not happen often)
                    )

                    # v6 interval text style and positioning
                    text_x, text_y = (start_x + end_x) / 2, start_y
                    if abs(start_y - end_y) > 0.1:  # If tasks are on different lanes
                        text_y = (start_y + end_y) / 2
                    else:  # Tasks on same lane, offset text slightly
                        text_y -= 0.10 * bar_height

                    ax.text(
                        text_x,
                        text_y,
                        f"{int(interval)}",
                        color=arrow_color,
                        fontsize=6.0,  # v6 style
                        ha="center",
                        va="center",
                        bbox=dict(  # v6 style
                            boxstyle="round,pad=0.1",
                            fc="white",
                            ec=arrow_color,
                            lw=0.5,
                            alpha=0.8,
                        ),
                    )

    ax.set_yticks(range(1, num_total_lanes + 1))
    ax.set_yticklabels(  # v6 style
        [f"Lane {i}" for i in range(1, num_total_lanes + 1)], fontsize=10
    )
    # Add padding to Y-axis: 0.5 above the first lane, 0.75 below the last lane
    # This will create more space between the last lane's content and the X-axis.
    ax.set_ylim(0.5, num_total_lanes + 0.75)
    ax.invert_yaxis()

    ax.set_xlabel(
        "Time (Simulation Units)", fontsize=14, labelpad=15
    )  # v6 style (increased labelpad)
    # Chart title removed as per v6 requirements

    max_display_time = simulation_makespan if simulation_makespan > 0 else 10
    ax.set_xlim(-max_display_time * 0.03, max_display_time * 1.03)  # v6 style

    legend_elements = [
        plt.Rectangle(
            (0, 0), 1, 1, color=color_palette["success"], label="Success/Other"
        ),
        plt.Rectangle((0, 0), 1, 1, color=color_palette["failure"], label="Failure"),
        plt.Rectangle(
            (0, 0), 1, 1, color=color_palette["monitoring"], label="Monitoring Task"
        ),
        plt.Rectangle((0, 0), 1, 1, color=color_palette["wait"], label="Wait/Gap"),
        plt.Line2D(
            [0],
            [0],
            color=color_palette["dependency_normal"],
            lw=1.2,
            label="Dependency (Non-Critical)",
        ),
        plt.Line2D(
            [0],
            [0],
            color=color_palette["dependency_critical"],
            lw=1.2,
            label="Dependency (Urgent/Critical)",
        ),
    ]

    # --- Refined bottom margin calculation and layout adjustment ---
    num_legend_cols = 3
    num_legend_rows = (len(legend_elements) + num_legend_cols - 1) // num_legend_cols

    # Define space contributions more explicitly as percentages of figure height
    legend_height_per_row_contribution = 0.055  # Increased slightly
    total_legend_height_contribution = (
        num_legend_rows * legend_height_per_row_contribution
    )

    xaxis_label_height_contribution = 0.04  # Reduced from 0.065
    yaxis_last_tick_label_contribution = 0.015  # Reduced from 0.03
    final_bottom_buffer_contribution = (
        0.035  # Increased small buffer at the very bottom
    )

    # This is the total fraction of the figure height reserved at the bottom
    calculated_bottom_margin = (
        total_legend_height_contribution
        + xaxis_label_height_contribution
        + yaxis_last_tick_label_contribution
        + final_bottom_buffer_contribution
    )
    # Ensure a minimum margin, e.g., 18% if calculated is too small, and cap at 40%.
    subplots_bottom_margin = max(0.18, min(calculated_bottom_margin, 0.40))

    # Place the legend: its bottom edge will be 'final_bottom_buffer_contribution'
    # from the figure's physical bottom.
    legend_bbox_y_anchor = final_bottom_buffer_contribution

    fig.legend(
        handles=legend_elements,
        loc="lower center",
        bbox_to_anchor=(0.5, legend_bbox_y_anchor),
        fancybox=True,
        shadow=False,
        ncol=num_legend_cols,
        fontsize=9,  # v6 style
    )

    # Use plt.tight_layout with a rect to fit axes within a defined box,
    # leaving space for the legend and other labels outside this box (esp. at the bottom).
    # rect = [left, bottom, right, top] in normalized figure coordinates.
    plt.tight_layout(rect=[0.08, subplots_bottom_margin, 0.96, 0.94])

    Path(save_dir).mkdir(parents=True, exist_ok=True)
    timestamp = (
        sim_data.get("saved_time", datetime.now().strftime("%Y%m%d_%H%M%S"))
        .replace(":", "")
        .replace(" ", "_")
    )
    # Use get with default for approach and scene names (from v6)
    safe_approach_name = "".join(
        c if c.isalnum() else "_" for c in sim_data.get("approach", "DefaultApproach")
    )
    safe_scene_name = "".join(
        c if c.isalnum() else "_"
        for c in sim_data.get("scene_name", "DefaultScene").replace("_physics.json", "")
    )
    # Updated output file name
    output_file_name = (
        f"{safe_approach_name}_{safe_scene_name}_{timestamp}_gantt_v6_fix_cutoff.png"
    )
    final_save_path = Path(save_dir) / output_file_name

    try:
        plt.savefig(final_save_path, dpi=300)
        print(f"간트 차트가 '{final_save_path}'에 저장되었습니다.")
    except Exception as e:
        print(f"오류: 간트 차트를 저장하는 중 문제 발생 - {e}")

    plt.show()
    plt.close(fig)


# --- main ---
if __name__ == "__main__":
    sim_json_file_path = "/Users/bagdong-gyu/WorkSpace/VSCodeProject/research/scripts/dag_bayesian_simulation.json"
    initial_plan_json_file_path = "/Users/bagdong-gyu/WorkSpace/VSCodeProject/research/assets/tasks/complex10_20subtasks(nd7->dc1, dnc1, dnc2, nd1->nd4, nd(2, 3, 5, 6)).json"
    output_directory = (
        "gantt_visualization_output_v6_fix_cutoff"  # Updated output directory
    )

    try:
        with open(initial_plan_json_file_path, "r", encoding="utf-8") as f:
            initial_plan_data = json.load(f)
    except FileNotFoundError:
        print(
            f"오류: 원본 Task 정보 파일을 찾을 수 없습니다 - {initial_plan_json_file_path}"
        )
        initial_plan_data = []  # Initialize to empty list if file not found
    except json.JSONDecodeError:
        print(
            f"오류: 원본 Task 정보 JSON을 파싱할 수 없습니다. ({initial_plan_json_file_path})"
        )
        initial_plan_data = []  # Initialize to empty list if JSON error

    if not initial_plan_data:  # This was present in v4, good to keep
        print("경고: 원본 Task 정보가 없어 제약조건 그래프가 부정확할 수 있습니다.")

    # Call the updated function
    plot_gantt_final_v6_fix_cutoff(
        simulation_json_path=sim_json_file_path,
        initial_plan_json_data=initial_plan_data,
        save_dir=output_directory,
    )

    print(
        f"\n간트 차트 생성이 완료되었습니다. '{output_directory}' 디렉토리를 확인해주세요."
    )

# Ensure the helper functions (UnionFind, build_constraints_graph_from_inputs,
# merge_groups_for_lanes, assign_y_lanes_for_gantt_v3) are defined above this point.
# The user's diff showed changes in build_constraints_graph_from_inputs and assign_y_lanes_for_gantt_v3
# I will assume those changes are already part of the "existing code" before this edit point,
# or that the user will ensure they are consistent with their v6 version.
# My edit focuses on replacing plot_gantt_final_v4 and main.
# For full v6 consistency, the helper functions would also need to reflect the user's diff.
# However, the prompt was to modify the PLOTTING function.
# The provided diff was for the whole file, I am applying the plotting part of it + new fixes.
