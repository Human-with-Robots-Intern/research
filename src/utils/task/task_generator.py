import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai

from utils.constants import (
    ESTIMATE_FILE_NAME,
    KNOWLEDGE_PATH,
    PROMPT_FILE_PATH,
    PROMPT_PATH,
    TASK_PATH,
)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_openai() -> openai.OpenAI:
    """Initialize OpenAI API client."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY not found in environment variables.")
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    return openai.OpenAI(api_key=openai_api_key)


client = initialize_openai()

# Task cache for deduplication
task_cache: Dict[int, List[Dict[str, Any]]] = {}


def load_file(file_path: Path, file_type: str) -> Any:
    """Load content from the specified file."""
    if not file_path.exists():
        logger.error(f"{file_type.capitalize()} file not found: {file_path}")
        raise FileNotFoundError(f"{file_type.capitalize()} file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file) if file_type == "json" else file.read()


def sanitize_file_name(file_name: str) -> str:
    """Sanitize file name to ensure compatibility."""
    return datetime.now().strftime("%Y-%m-%d_%H_%M_") + re.sub(
        r"[^\w\-_\.]+", "_", file_name
    )


def validate_output_format(output: Any) -> bool:
    """Validate the format of the generated task output."""
    if not isinstance(output, list):
        return False
    for task in output:
        if not isinstance(task, dict) or not {"Task", "Subtasks"}.issubset(task):
            return False
        for subtask in task.get("Subtasks", []):
            required_keys = {
                "Name",
                "Repetition",
                "Type",
                "Executions",
                "Duration",
                "TemporalConstraints",
            }
            if not isinstance(subtask, dict) or not required_keys.issubset(subtask):
                return False
            executions = subtask.get("Executions", {})
            if not isinstance(executions, dict) or not {
                "Objects",
                "PrimitiveActions",
            }.issubset(executions):
                return False
    return True


def classify_subtasks(
    output: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Classify subtasks into valid and invalid based on knowledge."""
    invalid_subtasks, valid_subtasks = [], []
    valid_actions = set(knowledge.get("Valid_actions", {}).keys())

    for task in output:
        for subtask in task.get("Subtasks", []):
            primitive_actions = subtask.get("Executions", {}).get(
                "PrimitiveActions", []
            )
            invalid_actions = [
                action
                for action in primitive_actions
                if not any(
                    action.startswith(valid_action) for valid_action in valid_actions
                )
            ]
            if invalid_actions:
                logger.debug(
                    f"Invalid actions in subtask '{subtask['Name']}': {invalid_actions}"
                )
                subtask["InvalidActions"] = invalid_actions
                invalid_subtasks.append(subtask)
            else:
                valid_subtasks.append(subtask)

    return valid_subtasks, invalid_subtasks


def regenerate_invalid_subtasks(
    invalid_subtasks: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Regenerate invalid subtasks using OpenAI API."""
    regenerated_subtasks = []
    valid_actions = ", ".join(knowledge.get("Valid_actions", {}).keys())

    for subtask in invalid_subtasks:
        invalid_actions = subtask.get("InvalidActions", [])
        regenerate_prompt = [
            {
                "role": "user",
                "content": (
                    f"The subtask contains invalid actions: {', '.join(invalid_actions)}.\n"
                    f"Valid actions are: {valid_actions}.\n"
                    "Please correct the invalid actions in the subtask below:\n"
                    f"{json.dumps(subtask, indent=4, ensure_ascii=False)}\n"
                ),
            }
        ]
        try:
            response = client.chat.completions.create(
                model="gpt-4o", messages=regenerate_prompt
            )
            regenerated_content = response.choices[0].message.content.strip()
            regenerated_content = regenerated_content.strip("```json").strip("```")
            new_subtask = json.loads(regenerated_content)
            regenerated_subtasks.append(new_subtask)
        except Exception as e:
            logger.error(f"Error during subtask regeneration: {e}")

    return regenerated_subtasks


def regenerate_subtasks_parallel(
    invalid_subtasks: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Regenerate invalid subtasks in parallel."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(
            lambda subtask: regenerate_invalid_subtasks([subtask], knowledge),
            invalid_subtasks,
        )
    return [subtask for result in results for subtask in result]


def cached_generate_task(
    full_prompt: List[Dict[str, str]], knowledge: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """Generate tasks using OpenAI API with caching."""
    prompt_hash = hash(json.dumps(full_prompt, sort_keys=True))
    if prompt_hash in task_cache:
        logger.info("Using cached result.")
        return task_cache[prompt_hash]

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o", messages=full_prompt
            )
            output_content = response.choices[0].message.content.strip()

            if "```json" in output_content:
                output_content = output_content.strip("```json").strip("```")

            output = json.loads(output_content)

            if validate_output_format(output):
                task_cache[prompt_hash] = output
                return output
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    logger.error("Failed to generate valid output after retries.")
    return None


def generate_task():
    """Generate tasks based on user input and knowledge base."""

    examples_prompt = load_file(Path(PROMPT_PATH) / PROMPT_FILE_PATH, "txt")
    knowledge = load_file(Path(KNOWLEDGE_PATH) / ESTIMATE_FILE_NAME, "json")

    user_input = input("Please enter the instructions: ").strip()
    if not user_input:
        logger.error("User input cannot be empty.")
        raise ValueError("User input cannot be empty.")

    full_prompt = [
        {"role": "system", "content": examples_prompt},
        {"role": "user", "content": f"# [Input]\n\n{user_input}"},
    ]

    output = cached_generate_task(full_prompt, knowledge)

    if output and validate_output_format(output):
        task_numbers = len(output)
        subtask_numbers = sum(len(task.get("Subtasks", [])) for task in output)
        output_file_name = f"_{task_numbers}tasks_{subtask_numbers}subtasks.json"
        output_file_path = Path(TASK_PATH) / output_file_name
        save_to_file(output, output_file_path)
        return output_file_name
    else:
        logger.error("Failed to generate output.")
        raise ValueError("Task generation failed.")


def save_to_file(data: Any, file_path: Path) -> None:
    """Save data to a JSON file."""
    os.makedirs(file_path.parent, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        logger.info(f"Output saved to {file_path}.")
    except IOError as e:
        logger.error(f"Error occurred while saving file: {e}")
        raise


if __name__ == "__main__":
    try:
        generate_task()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
