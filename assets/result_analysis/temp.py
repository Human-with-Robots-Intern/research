import os
import shutil
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def count_json_files_in_folders(base_path: str) -> Dict[str, int]:
    """주어진 경로 하위의 모든 폴더를 rglob으로 탐색하여 각 폴더 내 .json 파일의 개수를 반환합니다.

    Args:
        base_path (str): 탐색을 시작할 기준 경로.

    Returns:
        Dict[str, int]: 각 폴더 경로(str)를 key로, 해당 폴더 내 .json 파일 개수(int)를 value로 하는 딕셔너리.

    Raises:
        OSError: 파일 시스템 접근 중 오류가 발생할 경우 예외를 발생시킵니다.

    Example:
        >>> result = count_json_files_in_folders("/tmp")
        >>> for folder, count in result.items():
        ...     print(f"{folder}: {count}개")
    """
    logger = logging.getLogger(__name__)
    folder_json_count: Dict[str, int] = {}
    base = Path(base_path)

    try:
        # 모든 하위 폴더를 rglob로 탐색
        for folder in base.rglob("*"):
            if folder.is_dir():
                # 해당 폴더 내의 .json 파일 개수 세기
                json_files = list(folder.glob("*.json"))
                folder_json_count[str(folder)] = len(json_files)
                logger.info(f"폴더: {folder}, .json 파일 개수: {len(json_files)}")
                
    except Exception as e:
        logger.error(f"폴더 및 파일 탐색 중 오류 발생: {e}")
        raise

    return folder_json_count

def count_total_json_files(base_path: str) -> int:
    """주어진 경로 하위 전체에서 .json 파일의 총 개수를 반환합니다.

    Args:
        base_path (str): 탐색을 시작할 기준 경로.

    Returns:
        int: 발견된 모든 .json 파일의 총 개수.

    Raises:
        OSError: 파일 시스템 접근 중 오류가 발생할 경우 예외를 발생시킵니다.

    Example:
        >>> count_total_json_files("/tmp")
        42
    """
    logger = logging.getLogger(__name__)
    try:
        # 전체 하위 경로에서 .json 파일을 재귀적으로 모두 카운트
        total_count: int = sum(1 for _ in Path(base_path).rglob("*.json"))
        logger.info(f"전체 .json 파일 개수: {total_count}")
        return total_count
    except Exception as e:
        logger.error(f".json 파일 총 개수 계산 중 오류 발생: {e}")
        raise


def count_json_files_by_filename(base_path: str) -> Dict[str, int]:
    """주어진 경로 하위에서 파일명별 .json 파일의 개수를 계산하고 로그를 남깁니다.

    Args:
        base_path (str): 탐색을 시작할 기준 경로.

    Returns:
        Dict[str, int]: 파일명을 key로, 개수를 value로 하는 딕셔너리.

    Raises:
        OSError: 파일 시스템 접근 중 오류가 발생할 경우.

    Example:
        >>> result = count_json_files_by_filename("/tmp")
        >>> for filename, count in result.items():
        ...     print(f"{filename}: {count}개")
    """
    logger = logging.getLogger(__name__)
    filename_counts: Dict[str, int] = defaultdict(int)
    base = Path(base_path)

    try:
        for path in base.rglob("*.json"):
            filename_counts[path.name] += 1

        logger.info("--- 파일명별 .json 파일 개수 ---")
        for filename, count in sorted(filename_counts.items()):
            logger.info(f"{filename}: {count}개")
        logger.info("-----------------------------")

    except Exception as e:
        logger.error(f"파일명별 .json 파일 개수 계산 중 오류 발생: {e}")
        raise

    return dict(filename_counts)

def find_missing_simulation_files(base_path: str) -> List[str]:
    """'dag_bayesian_simulation.json'이 있는 경로에서 'cpm_simulation.json' 또는 'dag_edf_simulation.json'이 없는 경우 해당 경로를 찾습니다.

    Args:
        base_path (str): 탐색을 시작할 기준 경로.

    Returns:
        List[str]: 필요한 파일이 누락된 폴더 경로의 리스트.

    Raises:
        OSError: 파일 시스템 접근 중 오류가 발생할 경우.
    """
    logger = logging.getLogger(__name__)
    missing_files_folders: List[str] = []
    base = Path(base_path)

    try:
        logger.info("--- 누락된 시뮬레이션 파일 검사 시작 ---")
        # 'dag_bayesian_simulation.json' 파일을 모두 찾음
        for bayesian_file in base.rglob("dag_bayesian_simulation.json"):
            directory = bayesian_file.parent
            cpm_file = directory / "cpm_simulation.json"
            edf_file = directory / "dag_edf_simulation.json"

            # cpm_simulation.json 또는 dag_edf_simulation.json 파일이 없는 경우
            if not cpm_file.exists() or not edf_file.exists():
                missing_files_folders.append(str(directory))
                if not cpm_file.exists() and not edf_file.exists():
                    logger.warning(
                        f"경로에서 'cpm_simulation.json'와 'dag_edf_simulation.json' 파일 누락: {directory}"
                    )
                elif not cpm_file.exists():
                    logger.warning(f"경로에서 'cpm_simulation.json' 파일 누락: {directory}")
                else:  # not edf_file.exists():
                    logger.warning(
                        f"경로에서 'dag_edf_simulation.json' 파일 누락: {directory}"
                    )

        if not missing_files_folders:
            logger.info("모든 경로에 필요한 시뮬레이션 파일이 존재합니다.")
        logger.info("--- 누락된 시뮬레이션 파일 검사 완료 ---")

    except Exception as e:
        logger.error(f"누락된 시뮬레이션 파일 검사 중 오류 발생: {e}")
        raise

    return missing_files_folders


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 현재 파일이 위치한 디렉터리에서 실행
    current_dir: str = os.path.dirname(os.path.abspath(__file__))
    total_count: int = count_total_json_files(current_dir)
    print(f"전체 .json 파일 개수: {total_count}개")

    print("\n--- 파일명별 .json 파일 개수 ---")
    filename_counts = count_json_files_by_filename(current_dir)
    for filename, count in sorted(filename_counts.items()):
        print(f"{filename}: {count}개")
    print("-----------------------------")

    print("\n--- 누락된 시뮬레이션 파일이 있는 경로 ---")
    missing_folders = find_missing_simulation_files(current_dir)
    if missing_folders:
        for folder in missing_folders:
            print(folder)
    else:
        print("누락된 파일이 있는 경로를 찾을 수 없습니다.")
    print("------------------------------------")
