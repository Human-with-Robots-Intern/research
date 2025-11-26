import functools
import json
from pathlib import Path
from typing import Any, Callable

from ai2thor.controller import Controller

from src.utils.get_state import get_all_object_states, get_changed_object_states


def log_action_state(func: Callable) -> Callable:
    """1. Action 함수의 로직 시작 전, 현재 상태 확인 (get_state.py의 get_all_object_states 함수 사용)
            2. Action 함수 로직 종료 후, 상태 확인 (get_state.py의 get_changed_object_states 함수 사용)
            3. 상태 변경된 것만 JSON 파일에 저장
            예) [
        {
            "index": 0,
            "primitive_action": "NAVIGATE_TO Pot",
            "duration": 10.0,
            "state_change": []
        },
        {
            "index": 1,
            "primitive_action": "GRASP Pot",
            "duration": 10.0,
            "state_change": [
                {
                    "object_name": "Pot_aaa",
                    "property": {
                        "parentReceptacles": ["agent"],
                        "isFilledWithLiquid": false,
                        "iscooked": false,
                        "isToggled": false
                    }
                }
            ]
        }
    ]
    """

    @functools.wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        controller: Controller = self.controller
        log_path: Path = self.trajectory_log_json_path

        # 1. Action 함수의 로직 시작 전, 현재 상태 확인
        state_before = get_all_object_states(controller)

        # Execute the original action
        result = func(self, *args, **kwargs)
        duration = result if isinstance(result, (int, float)) else 0.0

        # 2. Action 함수 로직 종료 후, 상태 확인
        state_after = get_all_object_states(controller)

        # 3. 상태 변경된 것만 찾기
        state_changes = get_changed_object_states(state_before, state_after)

        # Log entry 형식 준비
        action_name = func.__name__
        action_args_str = ", ".join(
            [str(a) for a in args] + [f"{k}={v}" for k, v in kwargs.items()]
        )
        primitive_action_str = f"{action_name.upper()} {action_args_str}"

        # 기존 로그 데이터 불러오기
        log_data = []
        if log_path.exists() and log_path.stat().st_size > 0:
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            except json.JSONDecodeError:
                log_data = []

        if not isinstance(log_data, list):
            log_data = []

        next_index = len(log_data)

        log_entry = {
            "index": next_index,
            "primitive_action": primitive_action_str.strip(),
            "duration": duration,
            "state_change": state_changes,
        }

        log_data.append(log_entry)

        # 로그 파일 저장
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4)

        return result

    return wrapper
