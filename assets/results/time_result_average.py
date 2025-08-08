import json
from collections import defaultdict
from typing import Dict, List


def extract_action_durations(json_path: str) -> Dict[str, List[float]]:
    """
    Extracts the first word of each action and its duration from the primitive_action_log in the given JSON file.

    Args:
        json_path (str): Path to the JSON file.

    Returns:
        Dict[str, List[float]]: Dictionary mapping action types to a list of durations.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    action_durations: Dict[str, List[float]] = defaultdict(list)
    plans = data.get('plans', [])
    for plan in plans:
        primitive_action_log = plan.get('primitive_action_log', [])
        for entry in primitive_action_log:
            action_str = entry.get('action', '')
            duration = entry.get('duration', 0.0)
            action_type = action_str.split()[0] if action_str else ''
            if action_type:
                action_durations[action_type].append(duration)
    return action_durations


def extract_action_durations_from_files(json_paths: List[str]) -> Dict[str, List[float]]:
    """
    Aggregates action durations from multiple JSON files.
    """
    all_action_durations: Dict[str, List[float]] = defaultdict(list)
    for path in json_paths:
        action_durations = extract_action_durations(path)
        for action, durations in action_durations.items():
            all_action_durations[action].extend(durations)
    return all_action_durations


def print_action_durations_and_averages(action_durations: Dict[str, List[float]]) -> None:
    """
    Prints the durations for each action type and their average.

    Args:
        action_durations (Dict[str, List[float]]): Dictionary mapping action types to a list of durations.
    """
    for action, durations in action_durations.items():
        durations_str = ', '.join(f'{d:.2f}' for d in durations)
        avg = sum(durations) / len(durations) if durations else 0.0
        print(f"{action}: [{durations_str}] (avg: {avg:.2f})")
    # Print summary line with only averages
    summary = ', '.join(f'{action}: ({sum(durations) / len(durations):.2f})' for action, durations in action_durations.items() if durations)
    print(f"\nSummary averages: {summary}")


def main() -> None:
    """
    Main function to extract and print action durations and averages from the specified JSON files.
    """
    json_paths = (
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_chicken and do_the_laundry and move_sausage_to_plate and put_orange_bowl_on_sink and move_blue_bowl_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_chicken and do_the_laundry and move_sausage_to_plate and put_orange_bowl_on_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_chicken and move_sausage_to_plate and put_orange_bowl_on_sink and move_blue_bowl_to_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_sausage and do_the_laundry and move_chicken_to_plate and move_blue_bowl_to_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_sausage and do_the_laundry and move_chicken_to_plate and put_orange_bowl_on_sink and move_blue_bowl_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_sausage and do_the_laundry and move_chicken_to_plate and put_orange_bowl_on_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_sausage and move_chicken_to_plate and move_cup_to_sink and put_orange_bowl_on_sink and move_blue_bowl_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/cook_sausage and move_chicken_to_plate and put_orange_bowl_on_sink and move_blue_bowl_to_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/do_the_laundry and place_pan_on_stove and put_banana_on_plate and move_blue_bowl_to_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json",
        "/home/victus04/intern_ws/research_ros/research/assets/results/do_the_laundry and place_pan_on_stove and put_banana_on_plate and put_orange_bowl_on_sink and move_cup_to_sink_1/FloorPlan301/approach/cpm_ros.json"
    )
    action_durations = extract_action_durations_from_files(list(json_paths))
    print_action_durations_and_averages(action_durations)


if __name__ == "__main__":
    main()
