import json
import logging
import os
import re
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
    load_dotenv()
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("OPENAI_API_KEY not found in environment variables.")
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    client = openai.OpenAI(api_key=openai_api_key)
    return client


client = initialize_openai()


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
    invalid_subtasks: List[Dict[str, Any]],
    full_prompt: List[Dict[str, str]],
    knowledge: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Regenerate invalid subtasks."""
    new_subtasks = []
    valid_actions = list(knowledge.get("Valid_actions", {}).keys())
    for subtask in invalid_subtasks:
        invalid_actions = subtask.get("InvalidActions", [])
        regenerate_prompt = full_prompt + [
            {
                "role": "user",
                "content": (
                    "The following subtask contains disallowed actions:\n"
                    f"Disallowed actions: {', '.join(invalid_actions)}\n"
                    f"Allowed actions: {', '.join(valid_actions)}\n"
                    "Please modify the subtask to include only valid actions.\n"
                    "Keep the existing structure and content as much as possible and make only necessary changes.\n"
                    "\n[Subtask]\n"
                    f"{json.dumps(subtask, indent=4, ensure_ascii=False)}\n"
                    "\n[Instructions]\n"
                    "- Replace invalid actions in 'PrimitiveActions' with valid ones.\n"
                    "- Maintain the order and logic of actions as much as possible.\n"
                    "- Update 'Objects' if necessary.\n"
                    "- Return the result in JSON format.\n"
                    "- Do not include unnecessary comments or additional text in the output.\n"
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
            new_subtasks.append(new_subtask)
            logger.info(f"Successfully regenerated subtask '{subtask['Name']}'.")
        except Exception as e:
            logger.error(
                f"Error occurred while regenerating subtask '{subtask['Name']}': {e}"
            )
    return new_subtasks


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


def is_valid_output(output: List[Dict[str, Any]]) -> bool:
    """Validate if the output has a valid structure."""
    if not validate_output_format(output):
        return False
    for task in output:
        if not task["Subtasks"]:
            return False
    return True


def generate_and_validate_task(
    full_prompt: List[Dict[str, str]], knowledge: Dict[str, Any]
) -> Optional[List[Dict[str, Any]]]:
    """Generate tasks and validate their format and actions."""
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o", messages=full_prompt
            )
            output_content = response.choices[0].message.content.strip()
            output_content = output_content.strip("```json").strip("```")
            output = json.loads(output_content)

            if not validate_output_format(output):
                logger.warning(f"Attempt {attempt}: Output format is invalid.")
                full_prompt.append(
                    {
                        "role": "user",
                        "content": (
                            "The output format does not match the required format.\n"
                            "Please strictly follow the format and guidelines provided in the examples.\n"
                            "Do not include any additional text or explanations.\n"
                            "Return the result in the specified JSON format.\n"
                        ),
                    }
                )
                continue

            valid_subtasks, invalid_subtasks = validate_actions(output, knowledge)
            if invalid_subtasks:
                logger.info("Invalid actions detected. Regenerating subtasks...")
                regenerated_subtasks = regenerate_invalid_subtasks(
                    invalid_subtasks, full_prompt, knowledge
                )
                for task in output:
                    task["Subtasks"] = valid_subtasks + regenerated_subtasks

            return output
        except json.JSONDecodeError as e:
            logger.error(f"Attempt {attempt}: Failed to parse JSON: {e}")
            full_prompt.append(
                {
                    "role": "user",
                    "content": (
                        "The output could not be parsed as valid JSON.\n"
                        "Return only the JSON output in the specified format without any additional text or explanations.\n"
                        "Do not use code blocks or markdown formatting.\n"
                    ),
                }
            )
            continue
        except Exception as e:
            logger.error(f"Attempt {attempt}: Error occurred: {e}")
            return None
    logger.error(f"Failed to generate valid output after {max_retries} attempts.")
    return None


def generate_task():
    """Main function to generate tasks based on user input."""
    # Load prompt template and knowledge base
    prompt_file_path = Path(PROMPT_PATH) / "e2e_generator.txt"
    knowledge_file_path = Path(KNOWLEDGE_PATH) / "knowledge.json"
    examples_prompt = load_prompt(prompt_file_path)
    knowledge = load_knowledge(knowledge_file_path)

    # Get user input
    user_input = input("Please enter the instructions: ").strip()
    if not user_input:
        logger.error("User input cannot be empty.")
        raise ValueError("User input cannot be empty.")

    # Construct the prompt
    full_prompt = [
        {"role": "system", "content": examples_prompt},
        {"role": "user", "content": f"# [Input]\n\n{user_input}"},
    ]

    # Generate and validate tasks
    output = generate_and_validate_task(full_prompt, knowledge)

    # Save final validated output
    if output and is_valid_output(output):
        sanitized_name = sanitize_file_name(output[0].get("Task", "output"))
        output_file_path = Path(TASK_PATH) / f"task_{sanitized_name}.json"
        save_to_file(output, output_file_path)
        return sanitized_name
    else:
        logger.error("Failed to generate output.")
        raise ValueError("Task generation failed.")


if __name__ == "__main__":
    try:
        generate_task()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
