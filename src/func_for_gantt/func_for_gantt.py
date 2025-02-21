import os
import json
from utils.constants import GANTT_PATH
from src import cpm


def read_gantt_file(gantt_file):

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
    


def write_gantt_file(method_name, task_name, final_schedule, edges):
    # 받아야 되는 값
    # task_name (str)
    # final_schedule = {"subtask_name1" : [sceduler_time, ai2thor_time, real_time], "subtask_name2" : [sceduler_time, ai2thor_time, real_time],}
    # sceduler_time : str
    # ai2thor_time : str
    # real_time : str
    # 스케쥴러, ai2thor, real_time에 해당하는 실행 시간
    # 최종적으로 완성된 edges

    paths = cpm.paths(edges)

    gantt_file = GANTT_PATH / f"{method_name}.json"
    gantt_data = read_gantt_file(gantt_file)

    # cpm에 있는 all paths 만드는 거 가져와서 "constraints"에 넣기
    # for문 만들어서 gantt_data에 한번에 넣기.

    task_data = {}
    real_time = 0
    
    for subtask_name, times in final_schedule.items():
        task_data[subtask_name] = {"scheduler" : times[0], "ai2thor" : times[1]},
        real_time += times[2]            
                
    task_data["complete_schedule"] = list(final_schedule.keys()),
    task_data["constraints"] = paths #dependency 있는 애들끼리 묶어져 있기만 하면 됨
    task_data["real_time"] = real_time

    with open(gantt_file, "w") as f:
        gantt_data[task_name] = task_data
        json.dump(gantt_data, f, indent=4) 

            
            
