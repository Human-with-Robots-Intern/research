import copy
import dataclasses
import itertools
import math  # For inf comparison
from queue import PriorityQueue
from unittest.mock import MagicMock, PropertyMock, call, patch

import networkx as nx  # Import networkx
import pytest

# 필요한 데이터 클래스 및 핸들러 임포트
from models.dataclass import CompletedEntry  # Added CompletedEntry
from models.dataclass import SchedulingDue  # Deadline 추가
from models.dataclass import (  # src 경로 사용
    ActionResult,
    Candidate,
    SchedulerState,
    SimulationNode,
)

# 테스트 대상 모듈 임포트
from src.core.scheduler import Scheduler  # src 경로 사용
from models.task import Duration, Execution, Subtask  # Execution 추가
from src.scheduler.action_handler import ActionHandler  # src 경로 사용
from src.scheduler.constraint_handler import ConstraintHandler  # src 경로 사용
from src.scheduler.heuristic_manager import HeuristicManager  # src 경로 사용
from src.utils.config import EPSILON, LARGE_NUMBER  # src 경로 사용


# Fixtures
@pytest.fixture
def mock_action_handler():
    mock = MagicMock(spec=ActionHandler)
    mock_action_result = MagicMock(spec=ActionResult)
    mock_action_result.cumulative_time = 1.0
    mock_action_result.action_duration = 1.0
    mock_action_result.scene_positions = {
        "agent": (1, 0, 0),
        "target": (1, 0, 0),
    }  # 샘플 위치 추가
    mock_action_result.held_object = None
    mock_action_result.success = True
    mock.get_actions_info.return_value = mock_action_result
    # split_subtask_by_cutoff_time 모킹 (필요시)
    mock.split_subtask_by_cutoff_time.return_value = (MagicMock(), MagicMock())
    return mock


@pytest.fixture
def mock_constraint_handler():
    mock = MagicMock(spec=ConstraintHandler)
    # 기본 get_feasible_candidates 반환 설정 (빈 리스트)
    mock.get_feasible_candidates.return_value = ([], [])
    # get_earliest_start_time 모킹 (ConstraintHandler 내부에서 사용될 수 있음)
    # 기본 반환값: 시작 가능, non-critical, 완료된 선행
    mock.get_earliest_start_time.return_value = (0.0, False, "COMPLETED")
    mock.get_time_slots.return_value = []
    return mock


@pytest.fixture
def mock_heuristic_manager():
    mock = MagicMock(spec=HeuristicManager)
    # 기본 calc_heuristic 반환 설정
    mock.calc_heuristic.return_value = 10.0
    return mock


@pytest.fixture
def sample_subtask_factory():  # Changed to factory pattern
    """Factory for creating Subtask mocks"""

    def _create_subtask(
        name="SampleSub",
        duration=5.0,
        actions=None,
        type="Interaction",
        decomposed=False,
    ):
        sub = MagicMock(spec=Subtask)
        sub.name = name
        sub.subtask_type = type
        sub.execution = MagicMock(spec=Execution)
        if actions is None:
            sub.execution.primitive_actions = [f"ACTION {name}"]
        else:
            sub.execution.primitive_actions = actions
        sub.duration = MagicMock(spec=Duration)
        sub.duration.type = "Controllable"
        sub.duration.interval = duration
        sub.decomposed = decomposed
        # Make attributes readable via PropertyMock
        type(sub).name = PropertyMock(return_value=name)
        type(sub).subtask_type = PropertyMock(return_value=type)
        type(sub).execution = PropertyMock(return_value=sub.execution)
        type(sub).duration = PropertyMock(return_value=sub.duration)
        type(sub).decomposed = PropertyMock(return_value=decomposed)
        return sub

    return _create_subtask


@pytest.fixture
def sample_candidate_factory(sample_subtask_factory):  # Use subtask factory
    """Factory for creating Candidate objects"""

    def _create_candidate(
        subtask_name="SampleSub",  # Use name to create subtask
        duration=5.0,
        actions=None,
        type="Interaction",
        earliest_start=0.0,
        is_critical=False,
        deadline_time=float("inf"),
        deadline_reason=None,
    ):
        subtask = sample_subtask_factory(
            name=subtask_name, duration=duration, actions=actions, type=type
        )  # Create subtask inside
        deadline = SchedulingDue(due_date=deadline_time, subtask_name=deadline_reason)
        return Candidate(
            subtask=subtask,
            is_critical=is_critical,
            earliest_start_time=earliest_start,
            deadline=deadline,
        )

    return _create_candidate


@pytest.fixture
def initial_scheduler_state(sample_subtask_factory):  # Use subtask factory
    """Initial scheduler state fixture"""
    sub1 = sample_subtask_factory(name="TaskA", duration=5.0)
    sub2 = sample_subtask_factory(name="TaskB", duration=3.0)
    # scene_positions에 서브태스크 이름과 매칭되는 키가 있어야 함 (ActionHandler 등에서 사용)
    init_positions = {"agent": (0, 0, 0), "TaskA": (1, 0, 0), "TaskB": (0, 1, 0)}
    # Use nx.DiGraph() for constraints
    constraints_graph = nx.DiGraph()
    constraints_graph.add_node("TaskA")
    constraints_graph.add_node("TaskB")
    return SchedulerState(
        subtask=None,
        completed_entries=[],
        remaining_subtasks=[sub1, sub2],
        constraints=constraints_graph,  # Use nx.DiGraph
        current_time=0.0,
        scene_positions=init_positions,
        held_object=None,
    )


@pytest.fixture
def scheduler_instance(
    mock_action_handler, mock_constraint_handler, mock_heuristic_manager
):
    """테스트용 Scheduler 인스턴스 생성. 의존성 주입"""
    scheduler = Scheduler(
        beam_width=3,
        simulation_depth=2,
        nav_graph={},  # 모의 nav_graph
        action_handler=mock_action_handler,
        constraint_handler=mock_constraint_handler,
        heuristic_manager=mock_heuristic_manager,
    )
    # search_width 사용 확인
    assert scheduler.search_width == 3
    return scheduler


# 테스트 케이스
def test_scheduler_initialization(
    scheduler_instance,
    mock_action_handler,
    mock_constraint_handler,
    mock_heuristic_manager,
):
    """Scheduler 초기화 및 핸들러 주입 확인"""
    assert scheduler_instance.search_width == 3
    assert scheduler_instance.simulation_depth == 2
    # 핸들러가 올바르게 설정되었는지 확인
    assert scheduler_instance.action_handler is mock_action_handler
    assert scheduler_instance.constraint_handler is mock_constraint_handler
    assert scheduler_instance.cost_calculator is mock_heuristic_manager


# --- _simulate_search 테스트 ---
@patch("src.core.scheduler.PriorityQueue")
def test_simulate_search_no_candidates(
    mock_pq, scheduler_instance, initial_scheduler_state
):
    """실행 가능한 후보가 없을 때 None 반환 확인"""
    # get_feasible_candidates가 빈 리스트 반환하도록 설정
    scheduler_instance.constraint_handler.get_feasible_candidates.return_value = (
        [],
        [],
    )

    pq_instance = mock_pq.return_value
    pq_instance.empty.side_effect = [False, True]
    # get()이 SimulationNode 반환하도록 설정 (중요)
    init_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    pq_instance.get.return_value = init_node  # <<< 반환 타입 확인

    # _expand_candidates 호출 시 node.state 접근 확인
    # constraint_handler.get_feasible_candidates 호출 시 node 전달 확인
    result_node = scheduler_instance._simulate_search(initial_scheduler_state)

    assert result_node is None
    assert mock_pq.return_value.put.call_count == 1
    assert mock_pq.return_value.get.call_count == 1  # Should pass now

    # get_feasible_candidates 호출 시 curr_node.state 접근 확인
    scheduler_instance.constraint_handler.get_feasible_candidates.assert_called_once()
    call_args, _ = (
        scheduler_instance.constraint_handler.get_feasible_candidates.call_args
    )
    assert call_args[0] == init_node  # <<< SimulationNode 객체 전달 확인


@patch("src.core.scheduler.PriorityQueue")
@patch.object(Scheduler, "_expand_candidates")
def test_simulate_search_handles_large_number_cost(
    mock_expand,
    mock_pq,
    scheduler_instance,
    initial_scheduler_state,
    sample_candidate_factory,
):
    """휴리스틱 비용이 LARGE_NUMBER인 노드는 Beam Pruning에서 제외되는지 확인"""
    mock_expand.reset_mock()  # Mock 호출 횟수 초기화
    init_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=initial_scheduler_state,
    )

    # 확장 결과 모킹: 하나는 정상 비용, 하나는 LARGE_NUMBER
    sub_a = sample_candidate_factory("TaskA")
    state_a = initial_scheduler_state  # 간단히 상태 재사용
    node_a_normal = SimulationNode(
        heuristic_cost=10.0,
        depth=1,
        tie_breaker=1,
        parent_node=init_node,
        state=state_a,
    )
    node_b_large = SimulationNode(
        heuristic_cost=LARGE_NUMBER,
        depth=1,
        tie_breaker=2,
        parent_node=init_node,
        state=state_a,
    )

    # _expand_candidates가 정렬된 리스트 반환 가정
    mock_expand.return_value = [node_a_normal, node_b_large]

    # PQ 동작 모킹
    pq_instance = mock_pq.return_value
    pq_instance.empty.side_effect = [
        False,
        False,
        True,
    ]  # put(init), get(init), put(a_normal), empty
    pq_instance.get.return_value = init_node  # 첫 get은 init_node

    # constraint_handler 모킹 (후보 반환)
    cand_a = sample_candidate_factory("TaskA")
    cand_b = sample_candidate_factory("TaskB")
    scheduler_instance.constraint_handler.get_feasible_candidates.return_value = (
        [cand_a, cand_b],
        [],
    )

    # 시뮬레이션 깊이 1로 설정
    scheduler_instance.simulation_depth = 1
    # Beam Width 1로 설정하여 pruning 테스트
    scheduler_instance.search = 1

    result_node = scheduler_instance._simulate_search(initial_scheduler_state)

    # 결과는 node_a_normal 이어야 함 (최종 best_solutions에서 선택)
    # 주의: _simulate_search는 depth 1 도달 시 best_solutions에 추가. 최종 반환은 best_solutions 중 최저 비용.
    # 여기서는 depth 1 도달이 목적이므로 node_a_normal이 최종 반환될 가능성이 높음.
    # 만약 depth 0 에서 모든 작업 완료 시나리오면 init_node가 반환될 수도 있음.
    # 테스트를 명확히 하려면, node_a_normal도 depth=2로 만들고 depth=2 도달 시나리오 가정.
    node_a_normal.depth = 2  # 깊이 도달 가정
    pq_instance.empty.side_effect = [
        False,
        False,
        True,
    ]  # put(init), get(init), put(a_normal), get(a_normal), empty
    pq_instance.get.side_effect = [init_node, node_a_normal]

    result_node = scheduler_instance._simulate_search(initial_scheduler_state)
    assert result_node is node_a_normal

    # PQ에는 정상 비용 노드만 추가되어야 함
    pq_instance.put.assert_called_with(node_a_normal)
    # LARGE_NUMBER 비용 노드는 put 호출되지 않음
    calls = pq_instance.put.call_args_list
    assert not any(node_b_large in call.args for call in calls if call.args)

    assert mock_expand.call_count >= 1


@patch("src.core.scheduler.PriorityQueue")
@patch.object(Scheduler, "_expand_candidates")
def test_simulate_search_reaches_depth(
    mock_expand,
    mock_pq,
    scheduler_instance,
    initial_scheduler_state,
    sample_candidate_factory,
):
    """휴리스틱 비용이 LARGE_NUMBER인 노드는 Beam Pruning에서 제외되는지 확인"""
    mock_expand.reset_mock()  # Mock 호출 횟수 초기화
    init_node = SimulationNode(
        heuristic_cost=0.0,
        depth=0,
        tie_breaker=0,
        parent_node=None,
        state=initial_scheduler_state,
    )

    # 확장 결과 모킹: 하나는 정상 비용, 하나는 LARGE_NUMBER
    sub_a = sample_candidate_factory("TaskA")
    state_a = initial_scheduler_state  # 간단히 상태 재사용
    node_a_normal = SimulationNode(
        heuristic_cost=10.0,
        depth=1,
        tie_breaker=1,
        parent_node=init_node,
        state=state_a,
    )
    node_b_large = SimulationNode(
        heuristic_cost=LARGE_NUMBER,
        depth=1,
        tie_breaker=2,
        parent_node=init_node,
        state=state_a,
    )

    # _expand_candidates가 정렬된 리스트 반환 가정
    mock_expand.return_value = [node_a_normal, node_b_large]

    # PQ 동작 모킹
    pq_instance = mock_pq.return_value
    pq_instance.empty.side_effect = [
        False,
        False,
        True,
    ]  # put(init), get(init), put(a_normal), empty
    pq_instance.get.return_value = init_node  # 첫 get은 init_node

    # constraint_handler 모킹 (후보 반환)
    cand_a = sample_candidate_factory("TaskA")
    cand_b = sample_candidate_factory("TaskB")
    scheduler_instance.constraint_handler.get_feasible_candidates.return_value = (
        [cand_a, cand_b],
        [],
    )

    # 시뮬레이션 깊이 1로 설정
    scheduler_instance.simulation_depth = 1
    # Beam Width 1로 설정하여 pruning 테스트
    scheduler_instance.search = 1

    result_node = scheduler_instance._simulate_search(initial_scheduler_state)

    # 결과는 node_a_normal 이어야 함 (최종 best_solutions에서 선택)
    # 주의: _simulate_search는 depth 1 도달 시 best_solutions에 추가. 최종 반환은 best_solutions 중 최저 비용.
    # 여기서는 depth 1 도달이 목적이므로 node_a_normal이 최종 반환될 가능성이 높음.
    # 만약 depth 0 에서 모든 작업 완료 시나리오면 init_node가 반환될 수도 있음.
    # 테스트를 명확히 하려면, node_a_normal도 depth=2로 만들고 depth=2 도달 시나리오 가정.
    node_a_normal.depth = 2  # 깊이 도달 가정
    pq_instance.empty.side_effect = [
        False,
        False,
        True,
    ]  # put(init), get(init), put(a_normal), get(a_normal), empty
    pq_instance.get.side_effect = [init_node, node_a_normal]

    result_node = scheduler_instance._simulate_search(initial_scheduler_state)
    assert result_node is node_a_normal

    # PQ에는 정상 비용 노드만 추가되어야 함
    pq_instance.put.assert_called_with(node_a_normal)
    # LARGE_NUMBER 비용 노드는 put 호출되지 않음
    calls = pq_instance.put.call_args_list
    assert not any(node_b_large in call.args for call in calls if call.args)

    assert mock_expand.call_count >= 1


# --- _expand_candidates 테스트 ---
@patch.object(Scheduler, "_expand_single_subtask")
@patch.object(Scheduler, "_expand_single_wait")
def test_expand_candidates_feasible_only(
    mock_expand_wait,
    mock_expand_subtask,
    scheduler_instance,
    sample_candidate_factory,
):
    """Feasible 후보만 있고 Wait 없는 경우 테스트"""
    # Create subtasks first
    sub_a = sample_candidate_factory("TaskA")
    sub_b = sample_candidate_factory("TaskB")
    # Create candidates using the factory and subtasks
    cand_a = sample_candidate_factory("TaskA", earliest_start=0.0)
    cand_b = sample_candidate_factory("TaskB", earliest_start=0.0)
    feasible = [cand_a, cand_b]  # adjusted_start_time 오름차순 정렬됨 가정
    not_yet = []
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state = MagicMock(spec=SchedulerState)
    mock_node.state.current_time = 0.0

    # _expand_single_subtask가 모의 노드 반환하도록 설정
    mock_expansion_a = MagicMock(spec=SimulationNode)
    mock_expansion_a.heuristic_cost = 10.0
    mock_expansion_b = MagicMock(spec=SimulationNode)
    mock_expansion_b.heuristic_cost = 12.0
    mock_expand_subtask.side_effect = [mock_expansion_a, mock_expansion_b]

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    assert len(expansions) == 2
    assert mock_expand_subtask.call_count == 2
    mock_expand_wait.assert_not_called()
    # 호출 인자 확인 (정렬된 순서 cand_a, cand_b 로 호출 가정)
    mock_expand_subtask.assert_has_calls(
        [call(mock_node, cand_a), call(mock_node, cand_b)]
    )


@patch.object(Scheduler, "_expand_single_subtask")
@patch.object(Scheduler, "_expand_single_wait")
def test_expand_candidates_wait_only(
    mock_expand_wait,
    mock_expand_subtask,
    scheduler_instance,
    sample_candidate_factory,
):
    """Wait 후보만 있는 경우 테스트"""
    cand_c = sample_candidate_factory("TaskC", earliest_start=5.0)
    cand_d = sample_candidate_factory("TaskD", earliest_start=3.0)
    feasible = []
    not_yet = [cand_c, cand_d]  # 정렬되지 않은 상태
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state = MagicMock(spec=SchedulerState)
    mock_node.state.current_time = 0.0

    mock_wait_node = MagicMock(spec=SimulationNode)
    mock_wait_node.heuristic_cost = 15.0
    mock_expand_wait.return_value = mock_wait_node

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    assert len(expansions) == 1
    assert expansions[0] is mock_wait_node
    mock_expand_subtask.assert_not_called()
    # _expand_single_wait는 adjusted_start_time이 가장 빠른 cand_d로 호출되어야 함
    mock_expand_wait.assert_called_once_with(mock_node, cand_d)


@patch.object(Scheduler, "_expand_single_subtask")
@patch.object(Scheduler, "_expand_single_wait")  # Wait도 고려될 수 있으므로 mock 추가
def test_expand_candidates_immediate_critical_and_feasible(
    mock_expand_wait,
    mock_expand_subtask,
    scheduler_instance,
    sample_candidate_factory,
):
    """즉시 실행 Critical Task와 다른 Feasible Task가 함께 있는 경우 테스트 (src 로직 변경 반영)"""
    cand_a = sample_candidate_factory("TaskA", earliest_start=0.0)
    cand_crit = sample_candidate_factory(
        "Critical", is_critical=True, earliest_start=0.0
    )
    # 정렬된 순서: cand_crit, cand_a (또는 반대, 여기선 순서 무관하게 둘 다 처리되는지 확인)
    feasible = [cand_crit, cand_a]
    not_yet = []
    mock_node = MagicMock(spec=SimulationNode)
    mock_node.state = MagicMock(spec=SchedulerState)
    mock_node.state.current_time = 0.0

    # 두 번의 확장이 일어남 가정
    mock_crit_expansion = MagicMock(spec=SimulationNode)
    mock_crit_expansion.heuristic_cost = 8.0
    mock_a_expansion = MagicMock(spec=SimulationNode)
    mock_a_expansion.heuristic_cost = 10.0
    mock_expand_subtask.side_effect = [
        mock_crit_expansion,
        mock_a_expansion,
    ]  # 호출 순서대로 반환

    expansions = scheduler_instance._expand_candidates(mock_node, feasible, not_yet)

    # src 코드 변경: Critical 즉시 실행 필요해도 다른 feasible도 확장됨
    assert len(expansions) == 2
    assert mock_expand_subtask.call_count == 2
    mock_expand_wait.assert_not_called()  # not_yet 후보 없으므로 호출 안됨
    # Critical과 일반 Feasible 모두 확장 시도
    mock_expand_subtask.assert_has_calls(
        [call(mock_node, cand_crit), call(mock_node, cand_a)],
        any_order=True,  # 순서는 입력 정렬에 따라 다름
    )


# --- _expand_single_subtask 테스트 ---
@patch.object(Scheduler, "_should_expand_with_monitoring")
@patch.object(Scheduler, "_expand_subtask_with_monitoring")
@patch.object(Scheduler, "_expand_subtask_wo_monitoring")
def test_expand_single_subtask_routing(
    mock_expand_wo,
    mock_expand_w,
    mock_should,
    scheduler_instance,
    sample_candidate_factory,
):
    """_should_expand_with_monitoring 결과에 따른 라우팅 테스트"""
    candidate = sample_candidate_factory("Task")
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
def test_extract_state(initial_scheduler_state, sample_subtask_factory):
    """경로에서 depth=1 상태 추출 테스트"""
    # Create mock subtasks correctly
    root_sub = sample_subtask_factory(
        name="Root"
    )  # Use the fixture correctly (it's a factory now)
    step1_sub = sample_subtask_factory(name="Step1")
    step2_sub = sample_subtask_factory(name="Step2")

    # 경로 생성 (Root -> Node1 -> Node2)
    root_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    # Use dataclasses.replace
    state1 = dataclasses.replace(
        initial_scheduler_state, subtask=step1_sub, current_time=5.0
    )
    node1 = SimulationNode(10.0, 1, 1, root_node, state1)
    state2 = dataclasses.replace(state1, subtask=step2_sub, current_time=10.0)
    node2 = SimulationNode(20.0, 2, 2, node1, state2)

    # Correct Scheduler init call
    scheduler = Scheduler(beam_width=1, simulation_depth=2, nav_graph={})

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


# --- _expand_subtask_wo_monitoring 테스트 ---
def test_expand_subtask_wo_monitoring_success(
    scheduler_instance,
    mock_action_handler,
    mock_heuristic_manager,
    initial_scheduler_state,
    sample_candidate_factory,  # Use factory
):
    """_expand_subtask_wo_monitoring 성공 케이스 테스트"""
    sub_a = initial_scheduler_state.remaining_subtasks[0]  # TaskA
    candidate_a = sample_candidate_factory(subtask_name="TaskA", deadline_time=10.0)
    current_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)

    # Mock ActionResult 필드명 확인
    mock_action_result = MagicMock(spec=ActionResult)
    mock_action_result.cumulative_time = 5.0
    mock_action_result.action_duration = 5.0
    mock_action_result.scene_positions = {"agent": [1.0, 0.0, 0.0]}
    mock_action_result.held_object = None
    mock_action_result.success = True
    mock_action_handler.predict_duration.return_value = mock_action_result

    result_node = scheduler_instance._expand_subtask_wo_monitoring(
        current_node, candidate_a
    )

    assert result_node is not None
    assert result_node.parent_node is current_node
    assert result_node.depth == 1
    assert result_node.heuristic_cost == 15.0  # parent cost (0) + step cost (15)

    # 상태 검증
    new_state = result_node.state
    # name mock 객체의 return_value와 비교 시도
    new_state_subtask_name_val = new_state.subtask.name.return_value
    expected_subtask_name = "TaskA"
    assert (
        new_state_subtask_name_val == expected_subtask_name
    ), f"Expected subtask name '{expected_subtask_name}', got '{new_state_subtask_name_val}' from mock return_value"

    completed_subtask_name_val = new_state.completed_entries[
        0
    ].monitored_subtask.subtask.name.return_value
    assert (
        completed_subtask_name_val == expected_subtask_name
    ), f"Expected completed subtask name '{expected_subtask_name}', got '{completed_subtask_name_val}' from mock return_value"
    assert new_state.current_time == 5.0  # 현재 시간 + action 시간
    assert len(new_state.completed_entries) == 1
    assert new_state.completed_entries[0].schedule_start_time == 0.0
    assert new_state.completed_entries[0].schedule_end_time == 5.0
    assert len(new_state.remaining_subtasks) == 1
    assert new_state.remaining_subtasks[0].name == "TaskB"
    assert new_state.scene_positions["agent"] == (1, 0, 0)

    # 핸들러 호출 검증
    mock_action_handler.predict_duration.assert_called_once_with(
        current_node, sub_a.execution.primitive_actions
    )
    mock_heuristic_manager.calc_heuristic.assert_called_once()
    # calc_heuristic 호출 시 actual_duration 전달되는지 확인 (선택적 기능)
    # _, kwargs = mock_heuristic_manager.calc_heuristic.call_args
    # assert 'actual_duration' in kwargs and kwargs['actual_duration'] == 5.0


def test_expand_subtask_wo_monitoring_action_handler_fails(
    scheduler_instance,
    mock_action_handler,
    initial_scheduler_state,
    sample_candidate_factory,
):
    """ActionHandler.predict_duration가 None 반환 시 확장 실패 테스트"""
    candidate_a = sample_candidate_factory("TaskA")
    current_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    # ActionHandler가 None 반환하도록 설정
    mock_action_handler.predict_duration.return_value = None

    result_node = scheduler_instance._expand_subtask_wo_monitoring(
        current_node, candidate_a
    )

    assert result_node is None  # 확장에 실패하여 None 반환


def test_expand_subtask_wo_monitoring_heuristic_fails(
    scheduler_instance,
    mock_action_handler,
    mock_heuristic_manager,
    initial_scheduler_state,
    sample_candidate_factory,
):
    """HeuristicManager.calc_heuristic가 LARGE_NUMBER 반환 시 높은 비용의 노드 반환 테스트"""
    candidate_a = sample_candidate_factory("TaskA")
    current_node = SimulationNode(0.0, 0, 0, None, initial_scheduler_state)
    # HeuristicManager가 LARGE_NUMBER 반환하도록 설정
    mock_heuristic_manager.calc_heuristic.return_value = LARGE_NUMBER

    # ActionHandler는 정상 동작 가정
    mock_action_result = MagicMock(spec=ActionResult)
    mock_action_result.cumulative_time = 5.5
    mock_action_result.action_duration = 5.5
    mock_action_result.scene_positions = {"agent": [1.0, 0.0, 0.0]}
    mock_action_result.held_object = None
    mock_action_result.success = True
    mock_action_handler.predict_duration.return_value = mock_action_result

    result_node = scheduler_instance._expand_subtask_wo_monitoring(
        current_node, candidate_a
    )

    assert result_node is not None  # 노드는 생성됨
    assert result_node.heuristic_cost == LARGE_NUMBER  # 휴리스틱 비용이 그대로 반영됨
