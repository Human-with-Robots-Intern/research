"""Generate structured task JSON files for real-world experiments.

Reads from decomposed_final_revision_metadata_260416_realworld.json,
targets tasks_2_constraints_1 / tasks_3_constraints_1 / tasks_3_constraints_2,
and calls the LLM NUM_VERSIONS times per instruction to produce plan variations.
"""

import json
import os
import re
from pathlib import Path

import openai
from dotenv import load_dotenv

from src.utils.common import create_module_logger
from src.utils.config.constants import (
    ASSETS_PATH,
    ENV_PLACEHOLDER,
    PROMPT_PATH,
    SCENE_KNOWLEDGE_PATH,
)
from src.utils.task.task_validators import validate_output_format

load_dotenv()
logger = create_module_logger(__name__, module_log=True)

# ── Configuration ────────────────────────────────────────────────────────────
METADATA_FILE = (
    ASSETS_PATH / "tasks" / "decomposed_final_revision_metadata_260416_realworld.json"
)
PROMPT_FILE = PROMPT_PATH / "e2e_generator_ver13_real_one_shot.txt"
SCENE_NAME = "FloorPlan301"
ENV_FILE = (
    SCENE_KNOWLEDGE_PATH
    / "real_world"
    / "environment"
    / f"{SCENE_NAME}_physics_environment.json"
)
OUTPUT_FOLDER_PREFIX = "decomposed_final_revision_260416_realworld"
TARGET_CASES = [
    "tasks_2_constraints_1",
    "tasks_3_constraints_1",
    "tasks_3_constraints_2",
]
NUM_VERSIONS = 5
TEMPERATURE = 0.7
MODEL = "gpt-4o"
# ─────────────────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _call_openai(
    client: openai.OpenAI,
    messages: list,
    temperature: float = TEMPERATURE,
) -> list | None:
    """Call OpenAI and return parsed JSON output, retrying up to 5 times."""
    for attempt in range(1, 6):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            if match:
                content = match.group(1).strip()
            output = json.loads(content)
            if validate_output_format(output):
                return output
            logger.warning(f"[Attempt {attempt}] Output failed format validation.")
        except json.JSONDecodeError as e:
            logger.error(f"[Attempt {attempt}] JSON decode error: {e}")
        except Exception as e:
            logger.error(f"[Attempt {attempt}] Unexpected error: {e}")
    return None


def main() -> None:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY not found in environment variables.")
    client = openai.OpenAI(api_key=openai_api_key)

    # Build prompt with environment info injected
    prompt_template = _load_text(PROMPT_FILE)
    env_data = _load_json(ENV_FILE)
    env_str = json.dumps(env_data, indent=2, ensure_ascii=True)
    if ENV_PLACEHOLDER in prompt_template:
        prompt_template = prompt_template.replace(ENV_PLACEHOLDER, env_str)
    else:
        logger.warning(f"Placeholder '{ENV_PLACEHOLDER}' not found in prompt file.")

    metadata = _load_json(METADATA_FILE)
    all_cases = metadata.get("instructions_by_case", {})

    for case_key in TARGET_CASES:
        case_data = all_cases.get(case_key)
        if not case_data:
            logger.warning(f"Case '{case_key}' not found in metadata, skipping.")
            continue

        instructions = case_data.get("common", [])
        logger.info(f"### {case_key}: {len(instructions)} instructions ###")

        for idx, instruction in enumerate(instructions, start=1):
            logger.info(f"  [{idx}/{len(instructions)}] {instruction}")

            messages = [
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": f"# [Input]\n\n{instruction}"},
            ]

            file_stem = instruction.replace(" ", "_")

            for version in range(1, NUM_VERSIONS + 1):
                # Each version lives in its own top-level folder so filenames
                # stay clean (no _v suffix) and run_all can target each folder
                # independently via task_folder_name config.
                version_dir = (
                    ASSETS_PATH
                    / "tasks"
                    / f"{OUTPUT_FOLDER_PREFIX}_v{version}"
                    / case_key
                    / SCENE_NAME
                )
                version_dir.mkdir(parents=True, exist_ok=True)
                output_file = version_dir / f"{idx:02d}_{file_stem}.json"

                if output_file.exists():
                    logger.info(f"    v{version} already exists, skipping.")
                    continue

                result = _call_openai(client, messages)
                if result is None:
                    logger.error(
                        f"    Failed to generate v{version} for: {instruction}"
                    )
                    continue

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                logger.info(f"    Saved v{version}: {output_file.name}")

        logger.info(f"### Finished {case_key} ###\n")


if __name__ == "__main__":
    main()
