import os
import logging
from typing import NoReturn

def delete_folders_not_ending_with_1(base_path: str) -> NoReturn:
    """현재 폴더 내의 모든 하위 폴더 중 폴더명이 '_1'로 끝나지 않는 폴더를 삭제합니다.

    Args:
        base_path (str): 기준이 되는 디렉터리 경로.

    Returns:
        None

    Raises:
        OSError: 폴더 삭제 중 오류가 발생할 경우 예외를 발생시킵니다.

    Example:
        >>> delete_folders_not_ending_with_1(".")
    """
    logger = logging.getLogger(__name__)
    try:
        for entry in os.listdir(base_path):
            entry_path = os.path.join(base_path, entry)
            if os.path.isdir(entry_path):
                if not entry.endswith("_1"):
                    try:
                        # 폴더 삭제
                        import shutil
                        shutil.rmtree(entry_path)
                        logger.info(f"폴더 삭제됨: {entry_path}")
                    except Exception as e:
                        logger.error(f"폴더 삭제 실패: {entry_path}, 오류: {e}")
    except Exception as e:
        logger.error(f"폴더 목록 조회 중 오류 발생: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    current_dir: str = os.path.dirname(os.path.abspath(__file__))
    delete_folders_not_ending_with_1(current_dir)
