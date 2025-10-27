from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.utils.common import create_module_logger

logger = create_module_logger(__name__)

"""
GCRchecker.py는 각씬에서 각 task의 성공 여부를 체크하는 클래스입니다.
"""
class TaskSuccessChecker:
    """Task 성공 조건을 체크하는 클래스."""

    def __init__(self) -> None:
        """TaskSuccessChecker를 초기화합니다."""
        self.task_conditions = self._define_task_conditions()

    def _define_task_conditions(self) -> Dict[str, List[Dict[str, Any]]]:
        """각 task별 성공 조건을 정의합니다.
        
        Returns:
            task 이름을 키로 하고, 체크할 조건들의 리스트를 값으로 하는 딕셔너리
        """
        return {
            "boil_potato": [
                {"object_type": "Potato", "property": "isCooked", "expected_value": True},
                {"object_type": "Pot", "property": "isFilledWithLiquid", "expected_value": True},
            ],
            "boil_water_with_kettle": [
                {"object_type": "Kettle", "property": "parentReceptacles", "expected_value": "StoveBurner"},
            ],
            "cook_egg": [
                {"object_type": "Egg_Cracked", "property": "isCooked", "expected_value": True},
            ],
            "fill_pot_with_water": [
                {"object_type": "Pot", "property": "isFilledWithLiquid", "expected_value": True},
            ],
            
            "heat_the_potato_using_microwave": [
                {"object_type": "Potato", "property": "isCooked", "expected_value": True},
            ],
            "make_a_coffee": [
                {"object_type": "Mug", "property": "isFilledWithLiquid", "expected_value": True},
            ],
            
            "prepare_a_water_cup_with_mug": [
                {"object_type": "Mug", "property": "isFilledWithLiquid", "expected_value": True},
            ],
            "put_a_statue_on_the_table": [
                {"object_type": "Statue", "property": "parentReceptacles", "expected_value": "DiningTable"},
            ],
            "put_saltshaker_on_the_table": [
                {"object_type": "SaltShaker", "property": "parentReceptacles", "expected_value": "DiningTable"},
            ],
            
            "put_the_creditcard_on_the_countertop": [
                {"object_type": "CreditCard", "property": "parentReceptacles", "expected_value": "CounterTop"},
            ],
            "put_the_pencil_on_countertop": [
                {"object_type": "Pencil", "property": "parentReceptacles", "expected_value": "CounterTop"},
            ],
            "put_the_wine_bottle_inside_a_cabinet": [
                {"object_type": "WineBottle", "property": "parentReceptacles", "expected_value": "Cabinet"},
            ],
            "set_the_table": [
                {"object_type": "Fork", "property": "parentReceptacles", "expected_value": ["DiningTable", "CounterTop"]},
                {"object_type": "ButterKnife", "property": "parentReceptacles", "expected_value": ["DiningTable", "CounterTop"]},
            ],
            "throw_away_paper_towel_roll": [
                {"object_type": "PaperTowelRoll", "property": "parentReceptacles", "expected_value": "GarbageCan"},
            ],
            # 구제해야하는 task 들. 
            # 시뮬레이터 문제- 해결됨됨
            "put_the_book_in_cabinet": [
                {"object_type": "Book", "property": "parentReceptacles", "expected_value": "Cabinet"},
            ],
            # agent 몸뚱아리 문제 - 뒷걸음 치게 해서 다시 살림
            "put_the_wine_bottle_inside_a_cabinet": [
                {"object_type": "WineBottle", "property": "parentReceptacles", "expected_value": "Cabinet"},
            ],
            "put_salt_shaker_inside_the_safe": [
                {"object_type": "SaltShaker", "property": "parentReceptacles", "expected_value": "Safe"},
            ],
            "put_apple_and_lettuce_in_fridge": [
                {"object_type": "Apple", "property": "parentReceptacles", "expected_value": "Fridge"},
                {"object_type": "Lettuce", "property": "parentReceptacles", "expected_value": "Fridge"},
            ],
            # wash 관련 task들 - 적절한 gaol state를 정의하기 어렵다. 
            "wash_all_fork_and_spoon": [],
            "wash_apple_and_lettuce": [],
            "wash_two_ladles": [],
            # issue
            "heat_the_bread_using_microwave": [
                # {"object_type": "Bread", "property": "isCooked", "expected_value": True},
            ],
            "open_the_blinds": [ #처음부터 열려있었으면? 
                {"object_type": "Blinds", "property": "isOpen", "expected_value": True},
            ],
        }

    def load_state_from_json(self, file_path: Path) -> List[Dict[str, Any]]:
        """JSON 파일에서 상태 정보를 로드합니다.
        
        Args:
            file_path: JSON 파일 경로
            
        Returns:
            객체 상태 정보 리스트
        """
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state from {file_path}: {e}")
            return []

    def find_objects_by_type(self, state: List[Dict[str, Any]], object_type: str) -> List[Dict[str, Any]]:
        """특정 타입의 객체들을 찾습니다.
        
        Args:
            state: 상태 정보 리스트
            object_type: 찾을 객체 타입
            
        Returns:
            해당 타입의 객체들 리스트
        """
        # Use startswith to avoid false positives (e.g., 'Pot' matching 'Potato')
        return [obj for obj in state if obj.get("name", "").startswith(object_type)]

    def check_object_condition(
        self, 
        objects: List[Dict[str, Any]], 
        property_name: str, 
        expected_value: Any
    ) -> bool:
        """객체들의 특정 속성이 기대값과 일치하는지 확인합니다.
        
        Args:
            objects: 확인할 객체들
            property_name: 확인할 속성명
            expected_value: 기대값
            
        Returns:
            조건을 만족하는지 여부
        """
        if not objects:
            return False
            
        if isinstance(expected_value, list):
            # parentReceptacles: object's property is a list of strings; match by base name before '|'
            if property_name == "parentReceptacles":
                for obj in objects:
                    receptacles = obj.get(property_name) or []
                    # extract base names (before '|') for comparison
                    bases = [r.split('|', 1)[0] if isinstance(r, str) else r for r in receptacles]
                    # success if any expected value appears in any entry
                    for exp in expected_value:
                        if any((isinstance(r, str) and (exp in r or exp == base)) for r, base in zip(receptacles, bases)):
                            return True
                return False
            # Other properties: success if any object has a value in expected list
            return any(obj.get(property_name) in expected_value for obj in objects)

        # Single expected value
        if property_name == "parentReceptacles":
            # expected_value is a string; check containment within any of the entries
            exp = expected_value
            for obj in objects:
                receptacles = obj.get(property_name) or []
                for r in receptacles:
                    if isinstance(r, str) and (exp in r or r.split('|', 1)[0] == exp):
                        return True
            return False

        # For non-list properties, succeed if any matching object meets the expected value
        return any(obj.get(property_name) == expected_value for obj in objects)

    def check_task_success(
        self, 
        end_state: List[Dict[str, Any]], 
        task_name: str
    ) -> bool:
        """특정 task의 성공 여부를 확인합니다.
        
        Args:
            end_state: 최종 상태
            task_name: 확인할 task 이름
            
        Returns:
            task 성공 여부
        """
        if task_name not in self.task_conditions:
            logger.warning(f"Unknown task: {task_name}")
            return False
            
        conditions = self.task_conditions[task_name]
        
        # wash 관련 task들은 버림 처리
        if not conditions:
            return True
            
        for condition in conditions:
            object_type = condition["object_type"]
            property_name = condition["property"]
            expected_value = condition["expected_value"]
            
            # end_state에서 해당 타입의 객체들을 찾음
            objects = self.find_objects_by_type(end_state, object_type)
            
            if not self.check_object_condition(objects, property_name, expected_value):
                # logger.warning(f"task {task_name} failed: {object_type}.{property_name} != {expected_value}")
                # logger.warning(f"Found objects: {[obj.get('name') for obj in objects]}")
                # logger.warning(f"Object properties: {[obj.get(property_name) for obj in objects]}")
                return False

        return True

    def parse_instruction_to_tasks(self, instruction: str) -> List[str]:
        """instruction 문자열을 task 리스트로 파싱합니다.
        
        Args:
            instruction: " and "로 구분된 instruction 문자열
            
        Returns:
            task 이름들의 리스트
        """
        return [task.strip() for task in instruction.split(" and ")]

    def check_instruction_success(
        self, 
        instruction: str, 
        scene_name: str, 
        approach_name: str,
        states_dir: Path
    ) -> Dict[str, Any]:
        """특정 instruction의 성공률을 계산합니다.
        
        Args:
            instruction: instruction 문자열
            scene_name: 씬 이름
            approach_name: 접근법 이름
            
        Returns:
            성공률 정보를 담은 딕셔너리
        """
        tasks = self.parse_instruction_to_tasks(instruction)
        
        # 상태 파일 경로 구성
        states_dir = states_dir / instruction / scene_name / approach_name
        end_state_path = states_dir / "end_state.json"
        
        if not end_state_path.exists():
            logger.error(f"End state file not found for {instruction} in {scene_name}/{approach_name}")
            return {
                "instruction": instruction,
                "scene_name": scene_name,
                "approach_name": approach_name,
                "task_results": {},
                "overall_success_rate": 0.0,
                "successful_tasks": 0,
                "total_tasks": len(tasks),
                "error": "End state file not found"
            }
        
        # 상태 로드
        end_state = self.load_state_from_json(end_state_path)
        
        if not end_state:
            logger.error(f"Failed to load end state for {instruction} in {scene_name}/{approach_name}")
            return {
                "instruction": instruction,
                "scene_name": scene_name,
                "approach_name": approach_name,
                "task_results": {},
                "overall_success_rate": 0.0,
                "successful_tasks": 0,
                "total_tasks": len(tasks),
                "error": "Failed to load end state"
            }
        
        # 각 task 성공 여부 확인
        task_results = {}
        successful_count = 0
        
        for task in tasks:
            success = self.check_task_success(end_state, task)
            task_results[task] = success
            if success:
                successful_count += 1
        
        overall_success_rate = (successful_count / len(tasks)) * 100 if tasks else 0.0
        
        return {
            "instruction": instruction,
            "scene_name": scene_name,
            "approach_name": approach_name,
            "task_results": task_results,
            "overall_success_rate": overall_success_rate,
            "successful_tasks": successful_count,
            "total_tasks": len(tasks),
            "error": None
        }

    def process_all_instructions(self, states_folder: Path) -> None:
        """모든 instruction에 대해 성공률을 계산하고 결과를 저장합니다.
        
        Args:
            states_folder: states 디렉토리 경로
        """
        if not states_folder.exists():
            logger.error(f"States directory not found: {states_folder}")
            return
        
        all_results = []
        
        # 모든 instruction 폴더 순회
        for instruction_dir in states_folder.iterdir():
            if not instruction_dir.is_dir() or instruction_dir.name == "SRchecker.py":
                continue
                
            instruction = instruction_dir.name
            logger.info(f"Processing instruction: {instruction}")
            
            # 각 씬 폴더 순회
            for scene_dir in instruction_dir.iterdir():
                if not scene_dir.is_dir():
                    continue
                    
                scene_name = scene_dir.name
                logger.info(f"  Processing scene: {scene_name}")
                
                # 각 접근법 폴더 순회
                for approach_dir in scene_dir.iterdir():
                    if not approach_dir.is_dir():
                        continue
                        
                    approach_name = approach_dir.name
                    logger.info(f"    Processing approach: {approach_name}")
                    
                    # 성공률 계산
                    result = self.check_instruction_success(instruction, scene_name, approach_name, states_folder)
                    all_results.append(result)
                    
                    # 개별 결과 저장
                    output_dir = approach_dir / "task_success_rate.json"
                    with output_dir.open("w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    
                    logger.info(f"      Overall success rate: {result['overall_success_rate']:.1f}%")
        
        # 전체 결과 요약 저장
        summary = {
            "total_instructions": len(all_results),
            "average_success_rate": sum(r["overall_success_rate"] for r in all_results) / len(all_results) if all_results else 0.0,
            "results": all_results
        }
        
        summary_path = states_folder / "task_success_summary.json"
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Summary saved to: {summary_path}")
        logger.info(f"Average success rate across all instructions: {summary['average_success_rate']:.1f}%")


def main() -> None:
    """메인 실행 함수."""
    checker = TaskSuccessChecker()
    states_folder: Path = Path("assets/results/states140")
    checker.process_all_instructions(states_folder)


if __name__ == "__main__":
    main()
