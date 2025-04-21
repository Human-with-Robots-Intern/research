import copy
import itertools
from queue import PriorityQueue
from unittest.mock import MagicMock, call, patch

import pytest

# 필요한 데이터 클래스 및 핸들러 임포트
from core.dataclass import (
    ActionResult,
    Candidate,
    Duration,
    SchedulerState,
    SimulationNode,
    Subtask,
)

# 테스트 대상 모듈 임포트
from core.scheduler import Scheduler
from scheduler.action_handler import ActionHandler
from scheduler.constraint_handler import ConstraintHandler
from scheduler.heuristic_manager import HeuristicManager
from src.utils.config import EPSILON, LARGE_NUMBER


# Fixtures
@pytest.fixture
def mock_action_handler():
    mock = MagicMock(spec=ActionHandler)
    # 기본 get_actions_info 반환 설정
    mock_action_result = MagicMock(spec=ActionResult)
    mock_action_result.time_used = 1.0  # 기본 시간
    mock_action_result.scene_positions = {"agent": (1, 0, 0)}
    mock_action_result.held_object = None
    mock.get_actions_info.return_value = mock_action_result
    # split_subtask_by_cutoff_time 모킹 (필요시)
    mock.split_subtask_by_cutoff_time.return_value = (MagicMock(), MagicMock())
    return mock


@pytest.fixture
def mock_constraint_handler():
    mock = MagicMock(spec=ConstraintHandler)
    # 기본 get_feasible_candidates 반환 설정 (빈 리스트)
    mock.get_feasible_candidates.return_value = ([], [])
    # get_time_slots 모킹 (필요시)
    mock.get_time_slots.return_value = []
    return mock


@pytest.fixture
def mock_heuristic_manager():
    mock = MagicMock(spec=HeuristicManager)
    # 기본 calc_heuristic 반환 설정
    mock.calc_heuristic.return_value = 10.0  # 기본 휴리스틱 값
    return mock


@pytest.fixture
def sample_subtask(name="SampleSub"):
    # 간단한 모의 Subtask
    sub = MagicMock(spec=Subtask)
    sub.name = name
    sub.type = "Interaction"
    sub.execution.primitive_actions = [f"NAVIGATE_TO {name}"]
    sub.duration = Duration(type="Controllable", interval=5.0)
    sub.decomposed = False
    return sub


@pytest.fixture
def sample_candidate(subtask, adjusted_start=0.0, logical_start=0.0, is_critical=False):
    # Candidate 생성 헬퍼
    return Candidate(
        subtask=subtask,
        is_critical=is_critical,
        adjusted_start_time=adjusted_start,
        logical_start_time=logical_start,
        # deadline은 기본값 사용
    )


@pytest.fixture
def initial_scheduler_state(sample_subtask):
    """초기 스케줄러 상태 fixture"""
    sub1 = sample_subtask("TaskA")
    sub2 = sample_subtask("TaskB")
    return SchedulerState(
        subtask=None,  # 시작 시 subtask 없음
        completed_subtasks=[],
        remaining_subtasks=[sub1, sub2],
        constraints=MagicMock(),  # 모의 DiGraph
        current_time=0.0,
        scene_positions={"agent": (0, 0, 0), "TaskA": (1, 0, 0), "TaskB": (0, 1, 0)},
        held_object=None,
    )


@pytest.fixture
def scheduler_instance(
    mock_action_handler, mock_constraint_handler, mock_heuristic_manager
):
    """테스트용 Scheduler 인스턴스 생성"""
    return Scheduler(
        search_width=3,
        simulation_depth=2,
        action_handler=mock_action_handler,
        constraint_handler=mock_constraint_handler,
        heuristic_manager=mock_heuristic_manager,
        nav_graph={},  # 모의 nav_graph
    )


# 테스트 케이스
def test_scheduler_initialization(
    scheduler_instance,
    mock_action_handler,
    mock_constraint_handler,
    mock_heuristic_manager,
):
    """Scheduler 초기화 및 핸들러 주입 확인"""
    assert scheduler_instance.search == 3
    assert scheduler_instance.simulation_depth == 2
    assert scheduler_instance.action_handler is mock_action_handler
    assert scheduler_instance.constraint_handler is mock_constraint_handler
    assert scheduler_instance.cost_calculator is mock_heuristic_manager


# --- _simulate_search 테스트 --- (매우 복잡하여 핵심 경로 위주 테스트)
@patch("queue.PriorityQueue")  # PriorityQueue 모킹
def test_simulate_search_no_candidates(
    mock_pq, scheduler_instance, initial_scheduler_state
):
    """실행 가능한 후보가 없을 때 None 반환 확인"""
    # get_feasible_candidates가 빈 리스트 반환하도록 설정
    scheduler_instance.constraint_handler.get_feasible_candidates.return_value = (
        [],
        [],
    )

    result_node = scheduler_instance._simulate_search(initial_scheduler_state)

    assert result_node is None
    # PriorityQueue 상호작용 확인 (put 한 번, get 한 번)
    assert mock_pq.return_value.put.call_count == 1
    assert mock_pq.return_value.get.call_count == 1


@patch("queue.PriorityQueue")
@patch.object(Scheduler, "_expand_candidates")
def test_simulate_search_reaches_depth(
    mock_expand, mock_pq, scheduler_instance, initial_scheduler_state, sample_subtask
):
    """최대 깊이 도달 시 종료 및 최적해 반환 확인"""
    # 초기 노드 설정
    init_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    # 확장 결과 모킹 (depth 1에서 결과 반환)
    sub_a = sample_subtask("TaskA")
    state_a = initial_scheduler_state._replace(
        subtask=sub_a, current_time=5.0, remaining_subtasks=[sample_subtask("TaskB")]
    )
    node_a = SimulationNode(10.0, 1, 1, init_node, state_a)
    state_b = initial_scheduler_state._replace(
        subtask=sample_subtask("TaskB"), current_time=6.0, remaining_subtasks=[sub_a]
    )
    node_b = SimulationNode(12.0, 1, 2, init_node, state_b)
    mock_expand.return_value = [node_a, node_b]  # 정렬된 상태로 가정

    # PQ 동작 모킹
    pq_instance = mock_pq.return_value
    pq_instance.empty.side_effect = [
        False,
        False,
        False,
        True,
    ]  # put(init), get(init), put(a), put(b), get(a), get(b), empty
    pq_instance.get.side_effect = [init_node, node_a, node_b]

    # constraint_handler 모킹 (후보 반환)
    cand_a = sample_candidate(sub_a)
    cand_b = sample_candidate(sample_subtask("TaskB"))
    scheduler_instance.constraint_handler.get_feasible_candidates.return_value = (
        [cand_a, cand_b],
        [],
    )

    # 시뮬레이션 깊이 1로 설정하여 테스트
    scheduler_instance.simulation_depth = 1
    result_node = scheduler_instance._simulate_search(initial_scheduler_state)

    # 최적해는 비용이 낮은 node_a 여야 함
    assert result_node is node_a
    # expand_candidates는 한 번만 호출됨 (init_node 확장 시)
    mock_expand.assert_called_once_with(init_node, [cand_a, cand_b], [])
    # get은 3번 호출 (init, a, b)
    assert pq_instance.get.call_count == 3


# --- _expand_candidates 테스트 ---
# 이 함수는 내부적으로 _expand_single_* 함수들을 호출하므로, 해당 함수들을 모킹하여 테스트
@patch.object(Scheduler, "_expand_single_subtask")
@patch.object(Scheduler, "_expand_single_wait")
def test_expand_candidates_feasible_only(
    mock_expand_wait,
    mock_expand_subtask,
    scheduler_instance,
    sample_candidate,
    sample_subtask,
):
    """Feasible 후보만 있고 Wait 없는 경우 테스트"""
    cand_a = sample_candidate(sample_subtask("TaskA"))
    cand_b = sample_candidate(sample_subtask("TaskB"))
    feasible = [cand_a, cand_b]
    not_yet = []
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state.current_time = 0.0

    # _expand_single_subtask가 모의 노드 반환하도록 설정
    mock_expand_subtask.side_effect = [
        MagicMock(spec=SimulationNode),
        MagicMock(spec=SimulationNode),
    ]

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    assert len(expansions) == 2
    assert mock_expand_subtask.call_count == 2
    mock_expand_wait.assert_not_called()
    # 호출 인자 확인 (정렬된 순서대로 호출되는지 등)
    # 주의: 현재 _expand_candidates는 adjusted_start_time 오름차순 정렬 사용
    # 여기서는 cand_a, cand_b 순서로 전달되었다고 가정
    mock_expand_subtask.assert_has_calls(
        [call(mock_node, cand_a), call(mock_node, cand_b)], any_order=True
    )


@patch.object(Scheduler, "_expand_single_subtask")
@patch.object(Scheduler, "_expand_single_wait")
def test_expand_candidates_wait_only(
    mock_expand_wait,
    mock_expand_subtask,
    scheduler_instance,
    sample_candidate,
    sample_subtask,
):
    """Wait 후보만 있는 경우 테스트"""
    cand_c = sample_candidate(sample_subtask("TaskC"), adj_start=5.0)  # 아직 시작 불가
    cand_d = sample_candidate(sample_subtask("TaskD"), adj_start=3.0)  # 이게 더 빠름
    feasible = []
    not_yet = [cand_c, cand_d]
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state.current_time = 0.0

    # _expand_single_wait가 모의 노드 반환하도록 설정
    mock_wait_node = MagicMock(spec=SimulationNode)
    mock_expand_wait.return_value = mock_wait_node

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    assert len(expansions) == 1
    assert expansions[0] is mock_wait_node
    mock_expand_subtask.assert_not_called()
    # _expand_single_wait는 adjusted_start_time이 가장 빠른 cand_d로 호출되어야 함
    mock_expand_wait.assert_called_once_with(mock_node, cand_d)


@patch.object(Scheduler, "_expand_single_subtask")
def test_expand_candidates_immediate_critical(
    mock_expand_subtask, scheduler_instance, sample_candidate, sample_subtask
):
    """즉시 실행해야 하는 Critical Task가 있는 경우 테스트"""
    cand_a = sample_candidate(sample_subtask("TaskA"))
    # 현재 시간(0.0)과 조정된 시작 시간이 거의 같은 Critical Task
    cand_crit = sample_candidate(
        sample_subtask("Critical"), is_critical=True, adj_start=0.0
    )
    feasible = [cand_a, cand_crit]
    not_yet = []
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state.current_time = 0.0

    # Critical 확장 결과만 반환하도록 설정
    mock_crit_expansion = MagicMock(spec=SimulationNode)
    mock_expand_subtask.return_value = mock_crit_expansion

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    assert len(expansions) == 1
    assert expansions[0] is mock_crit_expansion
    # _expand_single_subtask는 Critical Task에 대해서만 한 번 호출됨
    mock_expand_subtask.assert_called_once_with(mock_node, cand_crit)


# --- _expand_single_subtask 테스트 ---
@patch.object(Scheduler, "_should_expand_with_monitoring")
@patch.object(Scheduler, "_expand_subtask_with_monitoring")
@patch.object(Scheduler, "_expand_subtask_wo_monitoring")
def test_expand_single_subtask_routing(
    mock_expand_wo,
    mock_expand_w,
    mock_should,
    scheduler_instance,
    sample_candidate,
    sample_subtask,
):
    """_should_expand_with_monitoring 결과에 따른 라우팅 테스트"""
    candidate = sample_candidate(sample_subtask("Task"))
    mock_node = MagicMock()

    # Case 1: 모니터링 필요 없음
    mock_should.return_value = False
    scheduler_instance._expand_single_subtask(mock_node, candidate)
    mock_expand_wo.assert_called_once_with(mock_node, candidate)
    mock_expand_w.assert_not_called()

    # Reset mocks
    mock_expand_wo.reset_mock()
    mock_expand_w.reset_mock()

    # Case 2: 모니터링 필요함
    mock_should.return_value = True
    scheduler_instance._expand_single_subtask(mock_node, candidate)
    mock_expand_w.assert_called_once_with(mock_node, candidate)
    mock_expand_wo.assert_not_called()


# _expand_subtask_wo_monitoring, _expand_subtask_with_monitoring, _expand_wait_* 등
# 개별 확장 함수들에 대한 상세한 테스트 케이스 추가 필요 (상태 변경, 비용 계산 등)
# 이 테스트들은 상태 객체와 핸들러 결과 모킹이 더 복잡해짐


# --- _extract_state 테스트 ---
def test_extract_state(initial_scheduler_state, sample_subtask):
    """경로에서 depth=1 상태 추출 테스트"""
    # 경로 생성 (Root -> Node1 -> Node2)
    root_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    state1 = initial_scheduler_state._replace(subtask=sample_subtask("Step1"))
    node1 = SimulationNode(10.0, 1, 1, root_node, state1)
    state2 = state1._replace(subtask=sample_subtask("Step2"))
    node2 = SimulationNode(20.0, 2, 2, node1, state2)

    scheduler = Scheduler(
        1, 1, MagicMock(), MagicMock(), MagicMock(), {}
    )  # 임시 스케줄러

    # Case 1: 경로 길이가 충분할 때
    extracted_state = scheduler._extract_state(node2)
    assert extracted_state is state1  # depth=1의 상태 반환

    # Case 2: 경로가 루트 뿐일 때
    extracted_state_root = scheduler._extract_state(root_node)
    assert extracted_state_root is initial_scheduler_state

    # Case 3: 입력 노드가 None일 때
    extracted_state_none = scheduler._extract_state(None)
    assert extracted_state_none is None


# _should_expand_with_monitoring 테스트 추가 필요
