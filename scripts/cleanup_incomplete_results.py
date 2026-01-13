import shutil
import argparse
from pathlib import Path


def cleanup_results(base_path: str = "assets/results", delete: bool = False) -> None:
    """
    assets/results 경로 하위의 폴더 구조를 탐색하여
    init_state.json은 있지만 end_state.json이 없는
    미완료된 실험 결과를 찾아 삭제합니다.

    Args:
        base_path: 탐색할 루트 경로
        delete: True일 경우 실제로 삭제 수행, False일 경우 대상만 출력
    """
    root_dir = Path(base_path)

    if not root_dir.exists():
        print(f"Error: 경로를 찾을 수 없습니다: {root_dir}")
        return

    print(f"Searching in: {root_dir.absolute()}")
    if delete:
        print("WARNING: 삭제 모드로 실행 중입니다. 미완료된 실험 폴더가 삭제됩니다.")
    else:
        print("INFO: 미리보기 모드입니다. 삭제하려면 --delete 옵션을 사용하세요.")
    print("-" * 50)

    count = 0
    
    # states 폴더 찾기
    state_dirs = [
        d for d in root_dir.iterdir() if d.is_dir() and d.name.startswith("states")
    ]
    state_dirs.sort()

    for state_dir in state_dirs:
        # Level 2: Case (e.g., tasks_3_constraints_2)
        for case_dir in state_dir.iterdir():
            if not case_dir.is_dir():
                continue

            # Level 3: Instruction (e.g., 08_heat_the_potato...)
            for instr_dir in case_dir.iterdir():
                if not instr_dir.is_dir():
                    continue

                # Level 4: Scene (e.g., FloorPlan18)
                for scene_dir in instr_dir.iterdir():
                    if not scene_dir.is_dir():
                        continue

                    # Level 5: Baseline Name (This is the experiment run)
                    for baseline_dir in scene_dir.iterdir():
                        if not baseline_dir.is_dir():
                            continue

                        init_path = baseline_dir / "init_state.json"
                        end_path = baseline_dir / "end_state.json"

                        # 조건: init_state.json 있음 AND end_state.json 없음
                        if init_path.exists() and not end_path.exists():
                            count += 1
                            print(f"[Found] {baseline_dir}")
                            
                            if delete:
                                try:
                                    shutil.rmtree(baseline_dir)
                                    print(f"  -> Deleted: {baseline_dir.name}")
                                except Exception as e:
                                    print(f"  -> Failed to delete: {e}")

    print("-" * 50)
    if delete:
        print(f"총 {count}개의 미완료 실험 폴더를 삭제했습니다.")
    else:
        print(f"총 {count}개의 미완료 실험 폴더가 발견되었습니다.")
        if count > 0:
            print("삭제하려면 --delete 옵션을 추가하여 실행하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="미완료된 실험 결과(init_state O, end_state X) 정리 스크립트")
    parser.add_argument("--base_path", type=str, default=None, help="탐색할 assets/results 경로")
    parser.add_argument("--delete", action="store_true", help="실제 삭제 수행")
    
    args = parser.parse_args()

    # 경로 설정
    if args.base_path:
        target_path = Path(args.base_path)
    else:
        # 스크립트 위치 기준 상대 경로 설정
        current_path = Path(__file__).resolve()
        project_root = current_path.parent.parent
        target_path = project_root / "assets" / "results"

    cleanup_results(str(target_path), args.delete)

