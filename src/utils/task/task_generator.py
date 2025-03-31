# utils/task/task_generator.py
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai
from dotenv import load_dotenv

from utils.common.logger import create_module_logger
from utils.config.constants import PROMPT_FILE_PATH, PROMPT_PATH, TASK_PATH, TOP_K
from utils.nlp.few_shot_retriever import FewShotRetriever
from utils.task.task_cache import check_cache, get_cache_key, store_cache

# 내부 모듈
from utils.task.task_validators import validate_output_format

# .env 파일 로딩 (OPENAI_API_KEY 등)
load_dotenv()

logger = create_module_logger(__name__)


def initialize_openai() -> openai.OpenAI:
    """
    OpenAI API 클라이언트를 초기화한다.
    """
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY not found in environment variables.")
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    return openai.OpenAI(api_key=openai_api_key)


class TaskGenerator:
    """
    태스크 생성 전반에 관한 로직을 관리하는 클래스.
    - OpenAI Client
    - Prompt 구성
    - 결과 검증/재생성
    - 캐싱
    등
    """

    def __init__(self, is_rag: bool = False):
        self.client = initialize_openai()
        self.is_rag = is_rag
        # 추가적으로 필요한 상태(예: knowledge 등) 여기서 관리 가능

    def load_file(self, file_path: Path, file_type: str) -> Any:
        """
        지정된 파일 경로에서 데이터를 로딩한다.
        """
        if not file_path.exists():
            raise FileNotFoundError(
                f"{file_type.capitalize()} file not found: {file_path}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            if file_type == "json":
                return json.load(f)
            else:
                return f.read()

    def generate_task(self, user_input: str) -> str:
        """
        유저 입력 + Knowledge Base + Prompt를 조합하여 태스크를 생성한다.
        결과를 파일에 저장하고, 파일명을 반환한다.
        """
        user_input = user_input.strip()
        if not user_input:
            raise ValueError("User input cannot be empty.")

        # Prompt(예제) 로드
        examples_prompt = self.load_file(Path(PROMPT_PATH) / PROMPT_FILE_PATH, "txt")

        # RAG 모드 활성화 시, FewShotRetriever 활용
        if self.is_rag:
            rag_system = FewShotRetriever()
            retrieved_few_shot_prompts = rag_system.generate_few_shot_prompts(
                user_input, top_k=TOP_K
            )
            examples_prompt = examples_prompt.replace(
                "<Example>", retrieved_few_shot_prompts
            )

        # Knowledge Base 로드
        # knowledge = self.load_file(Path(KNOWLEDGE_PATH) / ESTIMATE_FILE_NAME, "json")

        # 최종 OpenAI 프롬프트
        full_prompt = [
            {"role": "system", "content": examples_prompt},
            {"role": "user", "content": f"# [Input]\n\n{user_input}"},
        ]

        # 캐싱 체크
        prompt_key = get_cache_key(full_prompt)
        cached_result = check_cache(prompt_key)
        if cached_result:
            logger.info("Using cached result.")
            output = cached_result
        else:
            # OpenAI 호출
            output = self._call_openai(full_prompt)
            if output and validate_output_format(output):
                # 캐시에 저장
                store_cache(prompt_key, output)
            else:
                raise ValueError("Task generation failed. (Invalid Format)")

        # 파일로 저장
        time_stamp = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
        sanitized_input = re.sub(r"[^\w\-_\.]+", "_", user_input[:30])
        output_file_name = f"{time_stamp}_{sanitized_input}.json"
        output_file_path = Path(TASK_PATH) / output_file_name

        self.save_to_file(output, output_file_path)
        return output_file_name

    def _call_openai(
        self, full_prompt: List[Dict[str, str]]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        OpenAI API를 호출하여 태스크를 생성한다. (재시도 로직 포함)
        """
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=full_prompt,
                )
                output_content = response.choices[0].message.content.strip()

                # JSON 코드블록 제거
                if "```json" in output_content:
                    output_content = output_content.strip("```json").strip("```")

                output = json.loads(output_content)
                if validate_output_format(output):
                    return output

            except json.JSONDecodeError as e:
                logger.error(f"[Attempt {attempt}] JSON decoding failed: {e}")
            except Exception as e:
                logger.error(f"[Attempt {attempt}] Unexpected error: {e}")

        logger.error("Failed to generate valid output after retries.")
        return None

    def save_to_file(self, data: Any, file_path: Path) -> None:
        """
        JSON 파일로 결과를 저장한다.
        """
        os.makedirs(file_path.parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Output saved to {file_path}.")
