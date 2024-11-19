import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
from dotenv import load_dotenv

from utils.util import KNOWLEDGE_PATH, PROMPT_PATH, TASK_PATH

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_openai() -> openai.OpenAI:
    """Load OpenAI API key from environment variables and initialize the client."""
    # load_dotenv()
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY not found in environment variables.")
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    client = openai.OpenAI(api_key=openai_api_key)
    return client


client = initialize_openai()

# Task cache for deduplication
task_cache = {}


def load_prompt(file_path: Path) -> str:
    """Load prompt examples and context from the specified file."""
    if not file_path.exists():
        logger.error(f"Prompt file not found: {file_path}")
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def load_knowledge(file_path: Path) -> Dict[str, Any]:
    """Load knowledge base from the specified JSON file."""
    if not file_path.exists():
        logger.error(f"Knowledge file not found: {file_path}")
        raise FileNotFoundError(f"Knowledge file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def sanitize_file_name(file_name: str) -> str:
    """Convert a file name to a safe format."""
    return re.sub(r"[^\w\-_\.]", "_", file_name)


def validate_output_format(output: Any) -> bool:
    """Validate if the output adheres to the required format."""
    if not isinstance(output, list):
        return False
    for task in output:
        if not isinstance(task, dict) or not {"Task", "Subtasks"}.issubset(task):
            return False
        subtasks = task.get("Subtasks", [])
        if not isinstance(subtasks, list):
            return False
        for subtask in subtasks:
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


def validate_actions(
    output: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate actions in the output and classify them into valid and invalid subtasks."""
    invalid_subtasks = []
    valid_subtasks = []
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
                    f"Invalid actions found in subtask '{subtask['Name']}': {invalid_actions}"
                )
                subtask["InvalidActions"] = invalid_actions
                invalid_subtasks.append(subtask)
            else:
                valid_subtasks.append(subtask)
    return valid_subtasks, invalid_subtasks


def regenerate_invalid_subtasks(
    invalid_subtasks: List[Dict[str, Any]], knowledge: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Regenerate invalid subtasks."""
    regenerated_subtasks = []
    valid_actions = list(knowledge.get("Valid_actions", {}).keys())

    for subtask in invalid_subtasks:
        invalid_actions = subtask.get("InvalidActions", [])
        regenerate_prompt = [
            {
                "role": "user",
                "content": (
                    f"The subtask contains invalid actions: {', '.join(invalid_actions)}.\n"
                    f"Valid actions are: {', '.join(valid_actions)}.\n"
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


def cached_generate_and_validate_task(
    full_prompt: List[Dict[str, str]], knowledge: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """Check cache before generating tasks."""
    prompt_hash = hash(json.dumps(full_prompt, sort_keys=True))
    if prompt_hash in task_cache:
        logger.info("Using cached result.")
        return task_cache[prompt_hash]

    max_retries = 3
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
    """Main function to generate tasks based on user input."""
    prompt_file_path = Path(PROMPT_PATH) / "e2e_generator.txt"
    knowledge_file_path = Path(KNOWLEDGE_PATH) / "knowledge.json"
    examples_prompt = load_prompt(prompt_file_path)
    knowledge = load_knowledge(knowledge_file_path)

    user_input = input("Please enter the instructions: ").strip()
    if not user_input:
        logger.error("User input cannot be empty.")
        raise ValueError("User input cannot be empty.")

    full_prompt = [
        {"role": "system", "content": examples_prompt},
        {"role": "user", "content": f"# [Input]\n\n{user_input}"},
    ]

    output = cached_generate_and_validate_task(full_prompt, knowledge)

    if output and validate_output_format(output):
        sanitized_name = sanitize_file_name(output[0].get("Task", "output"))
        output_file_path = Path(TASK_PATH) / f"task_{sanitized_name}.json"
        save_to_file(output, output_file_path)
        return sanitized_name
    else:
        logger.error("Failed to generate output.")
        raise ValueError("Task generation failed.")


def save_to_file(data: Any, file_path: Path) -> None:
    """Save JSON data to the specified file."""
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
