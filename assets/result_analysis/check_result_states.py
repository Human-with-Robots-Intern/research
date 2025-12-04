from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CheckResult:
    """검사 결과를 담는 데이터 클래스.

    Attributes:
        both_exist: init_state.json과 end_state.json이 모두 존재하는 progprompt 디렉터리 목록.
        only_init: init_state.json만 존재하는 progprompt 디렉터리 목록.
        only_end: end_state.json만 존재하는 progprompt 디렉터리 목록.
    """

    both_exist: list[Path]
    only_init: list[Path]
    only_end: list[Path]


def _to_relative(paths: Iterable[Path], base: Path) -> list[Path]:
    """절대 경로 목록을 base 기준 상대 경로로 변환한다.

    Args:
        paths: 변환할 경로 이터러블.
        base: 기준이 되는 베이스 디렉터리.

    Returns:
        base 기준 상대 경로 목록.
    """
    rels: list[Path] = []
    for p in paths:
        try:
            rels.append(p.relative_to(base))
        except ValueError:
            rels.append(p)
    return rels


def check_progprompt_states(base_dir: Path) -> CheckResult:
    """states*/{index}_{instruction}/{scene}/progprompt 안의 init/end 동시 존재 여부를 확인한다.

    탐색 규칙:
      - 탐색 기준: {base_dir}/states*/
      - 검사 경로: **/progprompt/init_state.json, **/progprompt/end_state.json
      - progprompt 디렉터리 단위로 존재 여부를 판정한다.

    Args:
        base_dir: 베이스 디렉터리 (예: /home/dongkyu/pdk_ws/research/assets/results/llm_results_1110).

    Returns:
        CheckResult: both_exist, only_init, only_end 목록을 포함.
    """
    def _collect_progprompt_files(root: Path, filename: str) -> set[Path]:
        """states* 하위에서 progprompt/filename 파일을 모두 수집한다."""
        found: set[Path] = set()
        for state_dir in root.iterdir():
            if state_dir.is_dir() and state_dir.name.startswith("states"):
                # 깊이에 상관없이 progprompt/filename을 탐색
                for p in state_dir.rglob(f"progprompt/{filename}"):
                    if p.is_file():
                        found.add(p)
        return found

    # init/end 파일을 개별적으로 수집 (states*, states100 등 포함)
    init_files: set[Path] = _collect_progprompt_files(base_dir, "init_state.json")
    end_files: set[Path] = _collect_progprompt_files(base_dir, "end_state.json")

    # progprompt 디렉터리 단위로 집합 구성
    init_dirs: set[Path] = {p.parent for p in init_files}
    end_dirs: set[Path] = {p.parent for p in end_files}

    both_dirs: set[Path] = init_dirs & end_dirs
    only_init_dirs: set[Path] = init_dirs - end_dirs
    only_end_dirs: set[Path] = end_dirs - init_dirs

    return CheckResult(
        both_exist=sorted(both_dirs),
        only_init=sorted(only_init_dirs),
        only_end=sorted(only_end_dirs),
    )


def main() -> None:
    """CLI 엔트리포인트.

    사용 예:
        python check_states.py \
          --base /home/dongkyu/pdk_ws/research/assets/results/llm_results_1110 \
          --show-only-init
    """
    parser = argparse.ArgumentParser(
        description=(
            "assets/results/llm_results_1110/states_*/ 하위의 "
            "{index}_{instruction}/{scene}/progprompt 에서 "
            "init_state.json 과 end_state.json 동시 존재 여부를 확인합니다."
        )
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("assets/results/llm_results_1110"),
        help="베이스 디렉터리 (기본: assets/results/llm_results_1110)",
    )
    parser.add_argument(
        "--show-only-init",
        action="store_true",
        help="init_state.json만 존재하는 경로 목록을 출력합니다.",
    )
    parser.add_argument(
        "--show-only-end",
        action="store_true",
        help="end_state.json만 존재하는 경로 목록을 출력합니다.",
    )
    parser.add_argument(
        "--show-both",
        action="store_true",
        help="init/end가 모두 있는 경로 목록을 출력합니다.",
    )
    args = parser.parse_args()

    base_dir: Path = args.base.resolve()
    result: CheckResult = check_progprompt_states(base_dir)

    # 요약 출력
    print(f"[BASE] {base_dir}")
    print(f"- BOTH exist: {len(result.both_exist)}")
    print(f"- ONLY init:  {len(result.only_init)}")
    print(f"- ONLY end:   {len(result.only_end)}")

    if result.only_init or result.only_end:
        print("\n=> 전체 케이스에 대해 동시 존재(PASS)는 아닙니다.")
    else:
        print("\n=> 모든 케이스에서 init/end가 동시에 존재합니다. (PASS)")

    # 상세 목록 (요청 시)
    if args.show_both and result.both_exist:
        print("\n[BOTH exist] progprompt 디렉터리 목록:")
        for p in _to_relative(result.both_exist, base_dir):
            print(p)

    if args.show_only_init and result.only_init:
        print("\n[ONLY init] progprompt 디렉터리 목록:")
        for p in _to_relative(result.only_init, base_dir):
            print(p)

    if args.show_only_end and result.only_end:
        print("\n[ONLY end] progprompt 디렉터리 목록:")
        for p in _to_relative(result.only_end, base_dir):
            print(p)


if __name__ == "__main__":
    main()