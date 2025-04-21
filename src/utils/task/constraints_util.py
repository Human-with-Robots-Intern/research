from typing import List, Optional, Tuple  # 타입 힌팅을 위한 import 추가

import networkx as nx

from core.dataclass import CompletedEntry


def get_critical_start_info(
    subtask_name: str,
    completed: List[CompletedEntry],
    constraints: nx.DiGraph,
) -> Tuple[str, float]:
    """
    주어진 서브태스크(`subtask_name`)로 들어오는 제약 조건 중 가장 높은 'Interval' 값을 가진
    'IsCritical' 제약 조건을 식별합니다.

    해당 제약 조건의 시작 서브태스크 이름과, `completed` 목록에서 찾은
    해당 서브태스크의 완료 시간(`end_time`)을 반환합니다.

    Args:
        subtask_name: 대상 서브태스크의 이름.
        completed: 완료된 서브태스크 항목(`CompletedEntry` 객체) 목록.
        constraints: 제약 조건을 나타내는 NetworkX 방향 그래프 (`nx.DiGraph`).
                    엣지 데이터는 'info' 딕셔너리를 포함할 수 있으며,
                    이 딕셔너리에는 'IsCritical' (bool) 및 'Interval' (float) 키가
                    있을 수 있습니다.

    Returns:
        Tuple[str, float]: 가장 큰 인터벌을 가진 크리티컬 제약 조건의
                        시작 서브태스크 이름과 해당 서브태스크의 완료 시간 튜플.

    Raises:
        ValueError: 대상 서브태스크에 대해 들어오는 크리티컬 제약 조건이 없거나,
                    크리티컬 시작 서브태스크의 완료 시간이 `completed` 목록에 없는 경우.
    """
    # 크리티컬한 들어오는 엣지와 해당 인터벌 찾기
    critical_edges: List[Tuple[float, str]] = []
    # 엣지의 도착 노드(v)는 사용하지 않으므로 _ 로 받습니다.
    for u, _, data in constraints.in_edges(subtask_name, data=True):
        info = data.get("info", {})
        is_critical: bool = info.get("IsCritical", False)
        if is_critical:
            # Interval 값이 float 형태임을 가정합니다.
            interval: float = float(info.get("Interval", 0.0))
            # (interval, source_subtask_name) 튜플 저장
            critical_edges.append((interval, u))

    # 크리티컬 엣지가 있는지 확인
    if not critical_edges:
        raise ValueError(
            f"No critical incoming constraints found for subtask '{subtask_name}'"
        )

    # 가장 큰 인터벌을 가진 크리티컬 엣지 찾기
    # critical_edges가 비어있지 않음은 위에서 확인했습니다.
    # max 함수의 key로 튜플의 첫 번째 요소(interval)를 사용합니다.
    _, critical_start_sub_name = max(critical_edges, key=lambda item: item[0])

    # completed 리스트에서 critical_start_sub_name의 완료 시간 찾기
    # 제너레이터 표현식을 사용하여 메모리 효율성을 높일 수 있습니다.
    critical_start_entry: Optional[CompletedEntry] = next(
        (entry for entry in completed if entry.subtask.name == critical_start_sub_name),
        None,  # 찾지 못했을 경우 None 반환
    )

    # 완료된 항목을 찾았는지 확인
    if critical_start_entry is None:
        # 에러 메시지에 대상 서브태스크 이름도 포함하여 디버깅 용이성 향상
        raise ValueError(
            f"End time for critical start subtask '{critical_start_sub_name}' "
            f"not found in the completed list for target subtask '{subtask_name}'."
        )

    # CompletedEntry.end_time이 float 타입임을 가정합니다.
    critical_start_sub_end_time: float = critical_start_entry.end_time

    return critical_start_sub_name, critical_start_sub_end_time
