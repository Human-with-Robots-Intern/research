import json
from utils.constants import GANTT_PATH
from src import cpm
from pathlib import Path
from typing import Dict, List, Tuple
from utils import create_module_logger

# Set up logging configuration
log = create_module_logger(module_name=__name__, is_file_handler=True)

def read_gantt_file(gantt_file : Path) -> Dict:
    """
    Reads a Gantt chart JSON file.
    
    Args:
        gantt_file (Path): The path to the Gantt chart JSON file for write the information of schedule
    
    Returns:
        Dict: The parsed Gantt chart data.
    
    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file cannot be decoded.
    """

    if gantt_file.exists():
        try:
            with gantt_file.open("r", encoding="utf-8") as f:
                gantt_data = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Error decoding knowledge file: {e}", doc="", pos=0
            )
    else:
        raise FileNotFoundError(
            f"Knowledge file not found at {gantt_file}."
        )
    return gantt_data
    


def write_gantt_file(method_name : str, task_name : str, 
                     final_schedule : Dict[str, Tuple[str, str]], real_time : float, 
                     edges: List[Tuple[str, str]]) -> None:
    """
    Writes Gantt chart data to a JSON file.
    
    Args:
        method_name (str): The name of the method used for scheduling.
        task_name (str): The name of the current task.
        final_schedule (Dict[str, Tuple[str, str]]):
            - A dictionary mapping subtask names to their schedule times.
            - Each value is a tuple containing (scheduler_time, ai2thor_time).
        real_time (float): The actual execution time.
        edges (List[Tuple[str, str]]): A list representing task dependencies.
    
    Returns:
        None
    """
    log.info(f"Writing Gantt chart for method: {method_name}, task: {task_name}")
    paths = cpm.paths(edges)

    gantt_file = GANTT_PATH / f"{method_name}.json"
    gantt_data = read_gantt_file(gantt_file)

    task_data = {}
    real_time = 0
    
    for subtask_name, times in final_schedule.items():
        task_data[subtask_name] = {"scheduler" : times[0], "ai2thor" : times[1]}           
                
    task_data["complete_schedule"] = list(final_schedule.keys()),
    task_data["constraints"] = paths # Dependency realationships. There is no meaning of order.
    task_data["real_time"] = real_time

    with open(gantt_file, "w") as f:
        gantt_data[task_name] = task_data
        json.dump(gantt_data, f, indent=4) 
    log.info(f"Successfully wrote Gantt chart to {gantt_file}")

            
            
