import argparse
from unittest.mock import ANY, MagicMock, call, patch

import networkx as nx
import pytest

from src.core.dataclass import CompletedEntry, SchedulerState  # 필요한 클래스 임포트
from src.core.task import Duration, Execution, Subtask  # Subtask 생성 위해 임포트

# 테스트 대상 모듈 임포트 (경로 주의)
from src.dag_bayesian import main as dag_main
from src.dag_bayesian import parse_arguments

# --- Fixtures ---


@pytest.fixture
def mock_args():
    """기본 커맨드라인 인수 모의 객체"""
    args = argparse.Namespace()
    args.reset = False
    args.log_level = "INFO"
    return args


@pytest.fixture
def mock_scene_data():
    """모의 Scene 데이터"""
    data = MagicMock()
    data.file_name = "FloorPlan_Test_Scene"
    data.object_positions = {  # TaskUtil.get_init_state에 필요
        "agent": [0.0, 0.0, 0.0],
        "obj1": [1.0, 0.0, 0.0],
        "obj2": [0.0, 1.0, 0.0],
    }
    return data


@pytest.fixture
def mock_task_data():
    """모의 Task 데이터 (load_task_data_from_file 반환값)"""
    # TaskUtil.build_tasks_and_constraints가 처리할 수 있는 최소 형식
    return [{"Task": "TestTask", "Subtasks": []}]  # 실제 데이터 대신 간단한 구조 사용


@pytest.fixture
def mock_subtasks():
    """모의 Subtask 리스트 (TaskUtil.build_tasks_and_constraints 반환값)"""
    # 간단한 Subtask 두 개 생성 (실제 데이터 대신)
    exec1 = Execution(objects={"obj1": 1}, primitive_actions=["ACTION1 obj1"])
    dur1 = Duration(type="Fixed", interval=5.0)
    sub1 = Subtask("TestTask", "Sub1", 1, "TypeA", exec1, dur1)

    exec2 = Execution(objects={"obj2": 1}, primitive_actions=["ACTION2 obj2"])
    dur2 = Duration(type="Fixed", interval=3.0)
    sub2 = Subtask("TestTask", "Sub2", 1, "TypeB", exec2, dur2)

    # Init Subtask 추가 (get_init_state 에 의해 생성될 수 있음)
    exec_init = Execution(objects={}, primitive_actions=[])
    dur_init = Duration(type="Fixed", interval=0.0)
    sub_init = Subtask("Init", "Init", 1, "Init", exec_init, dur_init)

    return [sub_init, sub1, sub2]  # Init 포함


@pytest.fixture
def mock_constraints():
    """모의 제약 조건 그래프 (TaskUtil.build_tasks_and_constraints 반환값)"""
    # 간단한 그래프 (실제 데이터 대신)
    G = nx.DiGraph()
    G.add_node("Init")
    G.add_node("Sub1")
    G.add_node("Sub2")
    G.add_edge("Init", "Sub1", info={"Interval": 0, "IsCritical": False})
    G.add_edge("Sub1", "Sub2", info={"Interval": 0, "IsCritical": False})
    return G


@pytest.fixture
def mock_initial_state(mock_subtasks, mock_constraints, mock_scene_data):
    """모의 초기 SchedulerState (TaskUtil.get_init_state 반환값)"""
    # 첫번째 Subtask (Init) 를 completed 로 가정
    init_sub = mock_subtasks[0]
    completed_entry = CompletedEntry(
        subtask=init_sub,
        schedule_start_time=0.0,
        schedule_end_time=0.0,
        sim_start_time=0.0,
        sim_end_time=0.0,
        execution_status=True,
    )
    return SchedulerState(
        subtask=init_sub,  # 마지막으로 완료된 subtask
        completed_entries=[completed_entry],
        remaining_subtasks=mock_subtasks[1:],  # Init 제외
        constraints=mock_constraints,
        current_time=0.0,
        scene_positions=mock_scene_data.object_positions,
        held_object=None,
        agent_location="Start",
    )


# --- Test Function ---


@patch("src.dag_bayesian.parse_arguments")
@patch("src.dag_bayesian.get_user_scene_choice")
@patch("src.dag_bayesian.init_ai2thor_controller")
@patch("src.dag_bayesian.load_navigation_graph")
@patch("src.dag_bayesian.list_task_files")
@patch("src.dag_bayesian.get_user_task_choice")
@patch("src.dag_bayesian.load_task_data_from_file")
@patch("src.dag_bayesian.get_natural_language_from_task_file")
@patch("src.dag_bayesian.TaskUtil")  # TaskUtil 전체를 모킹
@patch("src.dag_bayesian.ActionHandler")
@patch("src.dag_bayesian.ConstraintHandler")
@patch("src.dag_bayesian.Agent")
@patch("src.dag_bayesian.HeuristicManager")
@patch("src.dag_bayesian.Scheduler")
@patch("src.dag_bayesian.execute_subtask")
@patch("src.dag_bayesian.result_save")
def test_main_workflow(
    mock_result_save,
    mock_execute_subtask,
    MockScheduler,
    MockHeuristicManager,
    MockAgent,
    MockConstraintHandler,
    MockActionHandler,
    MockTaskUtil,
    mock_get_nl,
    mock_load_task,
    mock_get_task,
    mock_list_task,
    mock_load_nav,
    mock_init_controller,
    mock_get_scene,
    mock_parse_args,
    # Fixtures
    mock_args,
    mock_scene_data,
    mock_task_data,
    mock_subtasks,
    mock_constraints,
    mock_initial_state,
):
    """dag_bayesian.py의 main 함수 전체 워크플로우 통합 테스트"""

    # 1. Mock 설정
    mock_parse_args.return_value = mock_args
    mock_get_scene.return_value = mock_scene_data
    mock_init_controller.return_value = MagicMock()  # AI2THOR Controller Mock
    mock_load_nav.return_value = {}  # Navigation Graph Mock
    mock_list_task.return_value = ["task1.json"]
    mock_get_task.return_value = ("task1.json", 1)  # 선택된 태스크 파일 이름, 번호
    mock_load_task.return_value = mock_task_data
    mock_get_nl.return_value = "Translated Test Task"

    # TaskUtil Mock 설정
    MockTaskUtil.build_tasks_and_constraints.return_value = (
        mock_subtasks[1:],
        mock_constraints,
    )  # Init 제외하고 반환
    MockTaskUtil.get_init_state.return_value = mock_initial_state

    # 핸들러, 에이전트, 스케줄러 Mock 인스턴스
    mock_action_handler_inst = MockActionHandler.return_value
    mock_constraint_handler_inst = MockConstraintHandler.return_value
    mock_agent_inst = MockAgent.return_value
    mock_heuristic_manager_inst = MockHeuristicManager.return_value
    mock_scheduler_inst = MockScheduler.return_value

    # 스케줄링 루프 제어 Mock 설정
    # 첫 번째 호출: Sub1을 포함한 next_state 반환
    # 두 번째 호출: Sub2를 포함한 next_state 반환
    # 세 번째 호출: None 반환하여 루프 종료
    next_state_sub1 = mock_initial_state._replace(
        subtask=mock_subtasks[1],  # 현재 subtask = Sub1
        completed_entries=mock_initial_state.completed_entries
        + [CompletedEntry(subtask=mock_subtasks[1])],
        remaining_subtasks=[mock_subtasks[2]],  # Sub2 만 남음
        current_time=5.0,  # 시간 경과 가정
    )
    next_state_sub2 = next_state_sub1._replace(
        subtask=mock_subtasks[2],  # 현재 subtask = Sub2
        completed_entries=next_state_sub1.completed_entries
        + [CompletedEntry(subtask=mock_subtasks[2])],
        remaining_subtasks=[],  # 남은 작업 없음
        current_time=8.0,  # 시간 경과 가정
    )
    mock_scheduler_inst.get_next_state.side_effect = [
        (next_state_sub1, 1.0),  # (state, computation_time)
        (next_state_sub2, 1.0),
        (None, 1.0),  # 루프 종료
    ]

    # execute_subtask Mock 설정 (성공, 고정 시간 반환)
    mock_execute_subtask.side_effect = [
        (5.0, True),  # Sub1 실행 결과 (sim_elapsed_time, execution_status)
        (3.0, True),  # Sub2 실행 결과
    ]

    # agent.bayesian_estimate Mock 설정 (호출되지 않거나, 호출 시 상태 그대로 반환)
    mock_agent_inst.bayesian_estimate.side_effect = lambda state: (state, None)

    # 2. 테스트 대상 함수 실행
    dag_main()

    # 3. 주요 함수 호출 검증
    mock_parse_args.assert_called_once()
    mock_get_scene.assert_called_once()
    mock_init_controller.assert_called_once_with(scene="FloorPlan")
    mock_load_nav.assert_called_once_with(mock_init_controller.return_value)
    mock_list_task.assert_called_once()
    mock_get_task.assert_called_once_with(["task1.json"])
    mock_load_task.assert_called_once_with("task1.json")
    mock_get_nl.assert_called_once_with("1")

    MockTaskUtil.build_tasks_and_constraints.assert_called_once_with(
        mock_task_data, mock_scene_data.file_name
    )
    MockTaskUtil.get_init_state.assert_called_once_with(
        mock_subtasks[1:], mock_constraints, mock_scene_data.object_positions
    )

    MockActionHandler.assert_called_once_with({})  # nav_graph
    MockConstraintHandler.assert_called_once_with(mock_action_handler_inst)
    MockAgent.assert_called_once_with(mock_constraint_handler_inst)
    MockHeuristicManager.assert_called_once_with(
        mock_constraint_handler_inst, mock_action_handler_inst, mock_agent_inst
    )
    MockScheduler.assert_called_once_with(
        ANY,  # BEAM_WIDTH
        ANY,  # SIMULATION_DEPTH
        nav_graph={},
        action_handler=mock_action_handler_inst,
        constraint_handler=mock_constraint_handler_inst,
        heuristic_manager=mock_heuristic_manager_inst,
    )

    # 스케줄링 루프 검증 (get_next_state 호출 횟수 수정)
    assert mock_scheduler_inst.get_next_state.call_count == 2
    # execute_subtask 호출 횟수 (2번)는 그대로 유지
    assert mock_execute_subtask.call_count == 2
    # execute_subtask 호출 인자 확인 (Sub1, Sub2 순서)
    mock_execute_subtask.assert_has_calls(
        [
            call(
                mock_init_controller.return_value, mock_subtasks[1], mock_args.log_level
            ),
            call(
                mock_init_controller.return_value, mock_subtasks[2], mock_args.log_level
            ),
        ]
    )

    # 결과 저장 함수 호출 검증 (result_args 내용 상세 비교)
    mock_result_save.assert_called_once()
    saved_args = mock_result_save.call_args[1]  # kwargs
    assert saved_args["task_name"] == "Translated Test Task"
    assert saved_args["approach_name"] == "dag_bayesian_simulation"
    assert saved_args["scene_name"] == "FloorPlan_Test_Scene"
    assert saved_args["computation_time"] == pytest.approx(2.0)
    # result_schedule 내용 검증 강화
    assert isinstance(saved_args["result_schedule"], list)
    assert len(saved_args["result_schedule"]) == 2
    # CompletedEntry 객체의 속성 검증 (예: 첫 번째 entry)
    entry1 = saved_args["result_schedule"][0]
    assert isinstance(entry1, CompletedEntry)
    assert entry1.subtask.name == "Sub1"  # subtask 객체 직접 비교 대신 이름 비교 등
    assert entry1.sim_start_time == pytest.approx(0.0)
    assert entry1.sim_end_time == pytest.approx(5.0)
    assert entry1.execution_status is True
    # constraints 검증
    assert saved_args["constraints"] == mock_constraints  # Mock 객체 비교
