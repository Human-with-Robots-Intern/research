import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
from dotenv import load_dotenv
from util import KNOWLEDGE_PATH, PROMPT_PATH, TASK_PATH

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_openai() -> None:
    load_dotenv()
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise EnvironmentError("환경 변수에서 OPENAI_API_KEY를 찾을 수 없습니다.")
    client = openai.OpenAI(api_key=openai_api_key)
    return client


client = initialize_openai()


def load_prompt(file_path: Path) -> str:
    """파일에서 프롬프트 예제와 컨텍스트를 로드합니다."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {file_path}")


def load_knowledge(file_path: Path) -> Dict[str, Any]:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(f"지식 파일을 찾을 수 없습니다: {file_path}")


def sanitize_file_name(file_name: str) -> str:
    """파일 이름을 저장 가능한 형태로 변환합니다."""
    return re.sub(r"[^\w\-_\.]", "_", file_name)


def validate_output_format(output: Any) -> bool:
    """
    출력이 필요한 형식을 따르는지 검증합니다.
    올바른 경우 True를 반환하고, 그렇지 않으면 False를 반환합니다.
    """
    # 출력은 리스트여야 합니다.
    if not isinstance(output, list):
        return False
    for task in output:
        if not isinstance(task, dict):
            return False
        required_task_keys = {"Task", "Subtasks"}
        if not required_task_keys.issubset(task.keys()):
            return False
        subtasks = task.get("Subtasks")
        if not isinstance(subtasks, list):
            return False
        for subtask in subtasks:
            if not isinstance(subtask, dict):
                return False
            required_subtask_keys = {
                "Name",
                "Repetition",
                "Type",
                "Executions",
                "Duration",
                "TemporalConstraints",
            }
            if not required_subtask_keys.issubset(subtask.keys()):
                return False
            executions = subtask.get("Executions")
            if not isinstance(executions, dict):
                return False
            required_execution_keys = {"Objects", "PrimitiveActions"}
            if not required_execution_keys.issubset(executions.keys()):
                return False
    return True


def validate_actions(
    output: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """GPT 출력의 액션들을 검증합니다."""
    invalid_subtasks = []
    valid_subtasks = []
    valid_actions = set(knowledge.get("Valid_actions", {}).keys())
    for task in output:
        for subtask in task.get("Subtasks", []):
            invalid_actions = [
                action
                for action in subtask["Executions"]["PrimitiveActions"]
                if not any(
                    action.startswith(valid_action) for valid_action in valid_actions
                )
            ]
            if invalid_actions:
                logger.debug(
                    f"서브태스크 '{subtask['Name']}'에서 유효하지 않은 액션 발견: {invalid_actions}"
                )
                subtask["InvalidActions"] = invalid_actions  # 유효하지 않은 액션 저장
                invalid_subtasks.append(subtask)
            else:
                valid_subtasks.append(subtask)
    return valid_subtasks, invalid_subtasks


def regenerate_invalid_subtasks(
    invalid_subtasks: List[Dict[str, Any]],
    full_prompt: List[Dict[str, str]],
    knowledge: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """유효하지 않은 서브태스크만 다시 생성하도록 GPT에 요청합니다."""
    new_subtasks = []
    valid_actions = list(knowledge.get("Valid_actions", {}).keys())
    for invalid_subtask in invalid_subtasks:
        # 유효하지 않은 액션 추출
        invalid_actions = invalid_subtask.get("InvalidActions", [])
        # 재생성을 위한 프롬프트 수정
        regenerate_prompt = full_prompt + [
            {
                "role": "user",
                "content": (
                    "The following subtask contains disallowed actions:\n"
                    f"Disallowed actions: {', '.join(invalid_actions)}\n"
                    f"Allowed actions: {', '.join(valid_actions)}\n"
                    "Please modify the following subtask to include only valid actions:\n"
                    "Please keep the existing structure and content where possible, and make only necessary changes.\n"
                    "\n[Subtask]\n"
                    f"{json.dumps(invalid_subtask, indent=4, ensure_ascii=False)}\n"
                    "\n[Instructions]\n"
                    "- Replace invalid actions in 'PrimitiveActions' with valid ones.\n"
                    "- Try to maintain the order and logic of the actions.\n"
                    "- Update 'Objects' if necessary.\n"
                    "- Return the final result in JSON format.\n"
                    "- Do not include unnecessary comments or additional text in the output.\n"
                ),
            }
        ]
        try:
            response = client.chat.completions.create(
                model="gpt-4o", messages=regenerate_prompt
            )
            regenerated_content = response.choices[0].message.content.strip()
            # GPT 응답에서 코드 블록 제거
            regenerated_content = regenerated_content.strip("```json").strip("```")
            new_subtask = json.loads(regenerated_content)
            new_subtasks.append(new_subtask)
            logger.info(
                f"서브태스크 '{invalid_subtask['Name']}'를 성공적으로 재생성했습니다."
            )
        except Exception as e:
            logger.error(
                f"서브태스크 '{invalid_subtask['Name']}' 재생성 중 오류 발생: {e}"
            )
    return new_subtasks


def save_to_file(data: Any, file_path: Path) -> None:
    """JSON 데이터를 파일에 저장합니다."""
    os.makedirs(file_path.parent, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        logger.info(f"출력이 {file_path}에 저장되었습니다.")
    except IOError as e:
        logger.error(f"파일 저장 중 오류 발생: {e}")
        raise


def generate_and_validate_task(
    full_prompt: List[Dict[str, str]], knowledge: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """태스크를 생성하고 액션 및 형식을 검증합니다."""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            # 태스크 생성
            response = client.chat.completions.create(
                model="gpt-4o", messages=full_prompt
            )
            output_content = response.choices[0].message.content.strip()
            # GPT 응답에서 코드 블록 제거
            output_content = output_content.strip("```json").strip("```")
            output = json.loads(output_content)

            # 출력 형식 검증
            if not validate_output_format(output):
                logger.warning(f"시도 {attempt+1}: 출력 형식이 유효하지 않습니다.")
                # LLM에 피드백 제공
                feedback_prompt = full_prompt + [
                    {
                        "role": "user",
                        "content": (
                            "The output format does not match the required format.\n"
                            "Please ensure that the output strictly follows the format and guidelines provided in the examples.\n"
                            "Do not include any additional text or explanations.\n"
                            "Return the result in the specified JSON format.\n"
                        ),
                    }
                ]
                full_prompt = feedback_prompt  # 다음 시도를 위한 프롬프트 업데이트
                continue  # 재시도

            # 생성된 출력의 액션 검증
            valid_subtasks, invalid_subtasks = validate_actions(output, knowledge)

            if invalid_subtasks:
                logger.info(
                    "유효하지 않은 액션이 감지되었습니다. 잘못된 서브태스크를 재생성합니다..."
                )
                regenerated_subtasks = regenerate_invalid_subtasks(
                    invalid_subtasks, full_prompt, knowledge
                )
                # 출력에서 서브태스크를 업데이트
                for task in output:
                    # 유효한 서브태스크와 재생성된 서브태스크로 교체
                    task["Subtasks"] = valid_subtasks + regenerated_subtasks

            return output
        except json.JSONDecodeError as e:
            logger.error(f"시도 {attempt+1}: GPT 출력의 JSON 파싱에 실패했습니다: {e}")
            # LLM에 피드백 제공
            feedback_prompt = full_prompt + [
                {
                    "role": "user",
                    "content": (
                        "The output could not be parsed as valid JSON.\n"
                        "Please ensure that you return only the JSON output in the specified format, without any additional text or explanations.\n"
                        "Do not include any code blocks or markdown formatting.\n"
                    ),
                }
            ]
            full_prompt = feedback_prompt  # 다음 시도를 위한 프롬프트 업데이트
            continue  # 재시도
        except Exception as e:
            logger.error(f"시도 {attempt+1}: 태스크 생성 중 오류 발생: {e}")
            return None
    logger.error(f"{max_retries}번의 시도 후에도 유효한 출력을 생성하지 못했습니다.")
    return None


def generate_task():
    """사용자 입력을 기반으로 태스크를 생성하는 메인 함수입니다."""
    # OpenAI API 초기화
    initialize_openai()

    # 프롬프트 템플릿 로드
    prompt_file_path = Path(PROMPT_PATH) / "e2e_generator.txt"
    knowledge_file_path = Path(KNOWLEDGE_PATH) / "knowledge.json"
    examples_prompt = load_prompt(prompt_file_path)
    knowledge = load_knowledge(knowledge_file_path)
    # 사용자 입력 받기
    user_input = input("지시사항을 입력해 주세요: ").strip()
    if not user_input:
        raise ValueError("사용자 입력은 비어 있을 수 없습니다.")

    # OpenAI API에 전달할 메시지 구성
    full_prompt = [
        {"role": "system", "content": examples_prompt},
        {"role": "user", "content": f"# [Input]\n\n{user_input}"},
    ]

    # 태스크 생성 및 검증
    output = generate_and_validate_task(full_prompt, knowledge)

    # 최종 검증된 출력 저장
    if output:
        sanitized_name = sanitize_file_name(user_input)
        output_file_path = Path(TASK_PATH) / f"task_{sanitized_name}.json"
        save_to_file(output, output_file_path)
    else:
        logger.error("출력이 생성되지 않았습니다.")


if __name__ == "__main__":
    try:
        generate_task()
    except Exception as e:
        logger.error(f"오류 발생: {e}")
