from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

try:
    # Optional dependency for Excel export
    from openpyxl import Workbook
except Exception:  # pragma: no cover - runtime availability is fine
    Workbook = None  # type: ignore[assignment]

from src.utils.common import create_module_logger
from src.utils.task.difficulty_analyzer import get_instruction_difficulty

logger = create_module_logger(__name__)


class TaskAnalyzer:
    """Task 성공률과 goal state를 분석하는 클래스."""

    def __init__(self) -> None:
        """TaskAnalyzer를 초기화합니다."""
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
            "open_the_blinds": [
                {"object_type": "Blinds", "property": "isOpen", "expected_value": True},
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
            "put_the_book_in_cabinet": [],
            "put_salt_shaker_inside_the_safe": [
                {"object_type": "SaltShaker", "property": "parentReceptacles", "expected_value": "Safe"},
            ],
            "put_apple_and_lettuce_in_fridge": [
                {"object_type": "Apple", "property": "parentReceptacles", "expected_value": "Fridge"},
                {"object_type": "Lettuce", "property": "parentReceptacles", "expected_value": "Fridge"},
            ],
            "wash_all_fork_and_spoon": [],
            "wash_apple_and_lettuce": [],
            "wash_two_ladles": [],
            "heat_the_bread_using_microwave": [
                {"object_type": "Bread", "property": "isCooked", "expected_value": True},
            ],
        }

    def load_summary_data(self, summary_path: Path) -> Dict[str, Any]:
        """요약 데이터를 로드합니다.
        
        Args:
            summary_path: 요약 JSON 파일 경로
            
        Returns:
            요약 데이터 딕셔너리
        """
        try:
            with summary_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load summary data from {summary_path}: {e}")
            return {}

    def analyze_task_performance(self, summary_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """각 task별 성능을 분석합니다.
        
        Args:
            summary_data: 요약 데이터
            
        Returns:
            task별 분석 결과
        """
        task_stats = {}
        
        # 모든 결과에서 task별 통계 수집
        for result in summary_data.get("results", []):
            task_results = result.get("task_results", {})
            
            for task_name, success in task_results.items():
                if task_name not in task_stats:
                    task_stats[task_name] = {
                        "total_attempts": 0,
                        "successful_attempts": 0,
                        "failed_attempts": 0
                    }
                
                task_stats[task_name]["total_attempts"] += 1
                if success:
                    task_stats[task_name]["successful_attempts"] += 1
                else:
                    task_stats[task_name]["failed_attempts"] += 1
        
        return task_stats

    def analyze_scene_performance(self, summary_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """각 scene별 task 성능을 분석합니다.
        
        Args:
            summary_data: 요약 데이터
            
        Returns:
            scene별 분석 결과
        """
        scene_stats = {}
        
        # 모든 결과에서 scene별 통계 수집
        for result in summary_data.get("results", []):
            scene_name = result.get("scene_name", "Unknown")
            task_results = result.get("task_results", {})
            
            if scene_name not in scene_stats:
                scene_stats[scene_name] = {}
            
            for task_name, success in task_results.items():
                if task_name not in scene_stats[scene_name]:
                    scene_stats[scene_name][task_name] = {
                        "total_attempts": 0,
                        "successful_attempts": 0,
                        "failed_attempts": 0
                    }
                
                scene_stats[scene_name][task_name]["total_attempts"] += 1
                if success:
                    scene_stats[scene_name][task_name]["successful_attempts"] += 1
                else:
                    scene_stats[scene_name][task_name]["failed_attempts"] += 1
        
        return scene_stats

    def analyze_difficulty_approach_performance(self, summary_data: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """난이도-approach 조합별 성능을 분석합니다.
        
        Args:
            summary_data: 요약 데이터
            
        Returns:
            난이도-approach 조합별 분석 결과
        """
        combination_stats: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        for result in summary_data.get("results", []):
            instruction = result.get("instruction", "")
            scene_name = result.get("scene_name", "")
            approach_name = result.get("approach_name", "unknown")
            overall_sr = result.get("overall_success_rate", 0.0)
            
            if not instruction or not scene_name:
                continue
            
            # instruction의 난이도 계산
            difficulty = get_instruction_difficulty(instruction, scene_name)
            
            # 통계 수집
            if difficulty not in combination_stats:
                combination_stats[difficulty] = {}
            
            if approach_name not in combination_stats[difficulty]:
                combination_stats[difficulty][approach_name] = {
                    "total_instructions": 0,
                    "successful_instructions": 0,
                    "total_sr": 0.0,
                    "sr_list": []
                }
            
            combination_stats[difficulty][approach_name]["total_instructions"] += 1
            combination_stats[difficulty][approach_name]["total_sr"] += overall_sr
            combination_stats[difficulty][approach_name]["sr_list"].append(overall_sr)
            
            if overall_sr == 100.0:
                combination_stats[difficulty][approach_name]["successful_instructions"] += 1
        
        # 평균 SR 계산
        for difficulty, approaches in combination_stats.items():
            for approach, stats in approaches.items():
                if stats["total_instructions"] > 0:
                    stats["average_sr"] = stats["total_sr"] / stats["total_instructions"]
                    stats["perfect_success_rate"] = (stats["successful_instructions"] / stats["total_instructions"]) * 100
                else:
                    stats["average_sr"] = 0.0
                    stats["perfect_success_rate"] = 0.0
        
        return combination_stats

    def print_difficulty_approach_analysis(self, combination_stats: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        """난이도-approach 조합별 분석 결과를 출력합니다.
        
        Args:
            combination_stats: 난이도-approach 조합별 분석 결과
        """
        print("\n=== 난이도-Approach 조합별 Success Rate 분석 ===")
        print(f"{'난이도':<10} {'Approach':<15} {'총 Instruction':<15} {'완벽 성공':<10} {'평균 SR':<10} {'완벽 성공률':<12}")
        print("-" * 90)
        
        # 난이도 순으로 정렬
        difficulty_order = ["simple", "normal", "hard", "unknown"]
        
        for difficulty in difficulty_order:
            if difficulty not in combination_stats:
                continue
            
            approaches = combination_stats[difficulty]
            # 평균 SR 순으로 정렬
            sorted_approaches = sorted(approaches.items(), key=lambda x: x[1]["average_sr"], reverse=True)
            
            for approach, stats in sorted_approaches:
                print(f"{difficulty:<10} {approach:<15} {stats['total_instructions']:<15} {stats['successful_instructions']:<10} "
                      f"{stats['average_sr']:<9.2f}% {stats['perfect_success_rate']:<11.2f}%")
        
        print("-" * 90)
        
        # 전체 통계
        total_instructions = sum(
            stats["total_instructions"] 
            for approaches in combination_stats.values() 
            for stats in approaches.values()
        )
        total_successful = sum(
            stats["successful_instructions"] 
            for approaches in combination_stats.values() 
            for stats in approaches.values()
        )
        total_sr_sum = sum(
            stats["total_sr"] 
            for approaches in combination_stats.values() 
            for stats in approaches.values()
        )
        
        overall_avg_sr = total_sr_sum / total_instructions if total_instructions > 0 else 0
        overall_perfect_sr = (total_successful / total_instructions) * 100 if total_instructions > 0 else 0
        
        print(f"{'전체':<10} {'전체':<15} {total_instructions:<15} {total_successful:<10} {overall_avg_sr:<9.2f}% {overall_perfect_sr:<11.2f}%")
        
        # 상세 분석
        print("\n=== 상세 분석 ===")
        for difficulty in difficulty_order:
            if difficulty not in combination_stats:
                continue
            
            print(f"\n{difficulty.upper()} 난이도:")
            approaches = combination_stats[difficulty]
            
            for approach, stats in approaches.items():
                print(f"  {approach}: 평균 SR {stats['average_sr']:.2f}%, 완벽 성공률 {stats['perfect_success_rate']:.2f}% "
                      f"({stats['successful_instructions']}/{stats['total_instructions']})")

    def generate_analysis_report(self, summary_data: Dict[str, Any]) -> Dict[str, Any]:
        """분석 보고서를 생성합니다.
        
        Args:
            summary_path: 요약 JSON 파일 경로
            
        Returns:
            분석 보고서
        """

        # task 성능 분석
        task_stats = self.analyze_task_performance(summary_data)
        
        # 분석 보고서 생성
        analysis_report = {}
        
        for task_name, stats in task_stats.items():
            goal_states = self.task_conditions.get(task_name, [])
            
            analysis_report[task_name] = {
                "goal_state": goal_states,
                "failure_frequency": f"{stats['failed_attempts']}/{stats['total_attempts']}",
                "success_rate": (stats['successful_attempts'] / stats['total_attempts']) * 100 if stats['total_attempts'] > 0 else 0.0,
                "total_attempts": stats['total_attempts'],
                "successful_attempts": stats['successful_attempts'],
                "failed_attempts": stats['failed_attempts']
            }
        
        return analysis_report

    def save_analysis_report(self, report: Dict[str, Any], output_path: Path = Path("assets/results/task_analysis_report.json")) -> None:
        """분석 보고서를 파일로 저장합니다.
        
        Args:
            report: 분석 보고서
            output_path: 출력 파일 경로
        """
        try:
            # 출력 디렉토리 생성
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Analysis report saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save analysis report: {e}")

    def print_analysis_summary(self, report: Dict[str, Any]) -> None:
        """분석 요약을 콘솔에 출력합니다.
        
        Args:
            report: 분석 보고서
        """
        print("\n=== Task 성능 분석 요약 ===")
        print(f"{'Task':<40} {'실패 빈도':<15} {'성공률':<10} {'Goal State 수':<12}")
        print("-" * 80)
        
        for task_name, data in report.items():
            goal_state_count = len(data['goal_state'])
            print(f"{task_name:<40} {data['failure_frequency']:<15} {data['success_rate']:<9.1f}% {goal_state_count:<12}")
        
        print("-" * 80)
        print(f"총 Task 수: {len(report)}")

    def print_scene_analysis(self, scene_stats: Dict[str, Dict[str, Any]]) -> None:
        """Scene별 분석 결과를 콘솔에 출력합니다.
        
        Args:
            scene_stats: scene별 분석 결과
        """
        print("\n=== Scene별 Task 성능 분석 ===")
        
        for scene_name in sorted(scene_stats.keys()):
            print(f"\n{scene_name}:")
            print("-" * 60)
            
            scene_tasks = scene_stats[scene_name]
            total_tasks = len(scene_tasks)
            failed_tasks = sum(1 for task_data in scene_tasks.values() if task_data['failed_attempts'] > 0)
            
            print(f"총 Task 수: {total_tasks}, 실패한 Task 수: {failed_tasks}")
            print()
            
            # 실패한 task들만 표시 (성공률 순으로 정렬)
            failed_task_list = []
            for task_name, task_data in scene_tasks.items():
                if task_data['failed_attempts'] > 0:
                    success_rate = (task_data['successful_attempts'] / task_data['total_attempts']) * 100
                    failed_task_list.append((task_name, task_data, success_rate))
            
            failed_task_list.sort(key=lambda x: x[2])  # 성공률 순으로 정렬
            
            if failed_task_list:
                print("실패한 Task들:")
                for task_name, task_data, success_rate in failed_task_list:
                    print(f"  {task_name}: {task_data['failed_attempts']}/{task_data['total_attempts']} 실패 (성공률: {success_rate:.1f}%)")
            else:
                print("모든 Task가 성공했습니다!")


    def export_difficulty_approach_to_excel(self, combination_stats: Dict[str, Dict[str, Dict[str, Any]]], output_dir: Path, filename: str = "difficulty_approach_analysis.xlsx") -> Path:
        """난이도-approach 분석 표를 엑셀로 저장합니다.

        Args:
            combination_stats: 난이도-approach 조합별 분석 결과
            output_dir: 출력 디렉토리 (task_success_summary.json이 있는 경로)
            filename: 저장할 엑셀 파일명

        Returns:
            저장된 엑셀 파일 경로

        Raises:
            RuntimeError: openpyxl이 설치되어 있지 않은 경우
        """

        if Workbook is None:
            raise RuntimeError("openpyxl 패키지가 필요합니다. `pip install openpyxl` 후 다시 시도하세요.")

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / filename

        wb = Workbook()
        ws = wb.active
        ws.title = "difficulty_approach"

        # Header
        ws.append(["난이도", "Approach", "총 Instruction", "완벽 성공", "평균 SR", "완벽 성공률"])

        # 정렬 규칙 동일 적용
        difficulty_order = ["simple", "normal", "hard", "unknown"]

        for difficulty in difficulty_order:
            if difficulty not in combination_stats:
                continue
            approaches = combination_stats[difficulty]
            sorted_approaches = sorted(approaches.items(), key=lambda x: x[1]["average_sr"], reverse=True)
            for approach, stats in sorted_approaches:
                ws.append([
                    difficulty,
                    approach,
                    int(stats["total_instructions"]),
                    int(stats["successful_instructions"]),
                    f"{stats['average_sr']:.2f} %",
                    f"{stats['perfect_success_rate']:.2f} %",
                ])

        # 전체 합계 행 추가
        total_instructions = sum(stats["total_instructions"] for approaches in combination_stats.values() for stats in approaches.values())
        total_successful = sum(stats["successful_instructions"] for approaches in combination_stats.values() for stats in approaches.values())
        total_sr_sum = sum(stats["total_sr"] for approaches in combination_stats.values() for stats in approaches.values())
        overall_avg_sr = total_sr_sum / total_instructions if total_instructions > 0 else 0
        overall_perfect_sr = (total_successful / total_instructions) * 100 if total_instructions > 0 else 0

        ws.append([None, None, None, None, None, None])
        ws.append(["전체", "전체", int(total_instructions), int(total_successful), f"{overall_avg_sr:.2f} %", f"{overall_perfect_sr:.2f} %"])

        wb.save(out_path)
        logger.info(f"Excel 저장 완료: {out_path}")
        return out_path

def main() -> None:
    """메인 실행 함수."""
    analyzer = TaskAnalyzer()
    
    # 요약 데이터 로드
    states_folder: Path = Path("assets/results/states140")
    summary_path: Path = states_folder / "task_success_summary.json"

    summary_data = analyzer.load_summary_data(summary_path)
    if not summary_data:
        logger.error("요약 데이터 로드에 실패했습니다.")
        return
    
    # Task별 분석 보고서 생성
    report = analyzer.generate_analysis_report(summary_data)
    
    if report:
        # 콘솔에 요약 출력
        analyzer.print_analysis_summary(report)
        
        # 파일로 저장
        analyzer.save_analysis_report(report)
        
        # Scene별 분석
        scene_stats = analyzer.analyze_scene_performance(summary_data)
        analyzer.print_scene_analysis(scene_stats)
        
        # 난이도-approach 조합별 분석 및 출력
        combination_stats = analyzer.analyze_difficulty_approach_performance(summary_data)
        analyzer.print_difficulty_approach_analysis(combination_stats)

        # 엑셀로 저장 (task_success_summary.json과 같은 경로)
        try:
            analyzer.export_difficulty_approach_to_excel(
                combination_stats,
                output_dir=summary_path.parent,
                filename="difficulty_approach_analysis.xlsx",
            )
        except Exception as e:
            logger.error(f"엑셀 저장 실패: {e}")
        
        # 성공률이 100%가 아닌 모든 task들의 상세 정보 출력
        print("\n=== 성공률이 100%가 아닌 Task 상세 정보 ===")
        failed_tasks = []
        
        for task_name, data in report.items():
            if data['success_rate'] < 100.0:
                failed_tasks.append((task_name, data))
        
        # 성공률 순으로 정렬 (낮은 성공률부터)
        failed_tasks.sort(key=lambda x: x[1]['success_rate'])
        
        for task_name, data in failed_tasks:
            print(f"\n{task_name}:")
            print(f"  실패 빈도: {data['failure_frequency']}")
            print(f"  성공률: {data['success_rate']:.1f}%")
            print(f"  Goal State:")
            if data['goal_state']:
                for i, goal in enumerate(data['goal_state'], 1):
                    print(f"    {i}. {goal}")
            else:
                print("    (Goal state가 정의되지 않음)")
        
        print(f"\n총 {len(failed_tasks)}개의 Task가 100% 성공률을 달성하지 못했습니다.")
    else:
        logger.error("분석 보고서 생성에 실패했습니다.")


if __name__ == "__main__":
    main()
