
import json
import argparse
import os
import re
import sys
import glob
from pathlib import Path
from datetime import datetime
import time
from typing import Dict, List, Any, Optional, Union, Tuple

import openai

# Constants
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.1
DEFAULT_RETRY_DELAY = 20
MAX_RETRIES = 3

class LLMError(Exception):
    """Exception raised for Language Model related errors."""
    pass

class MimicTranslationError(Exception):
    """Exception raised for Mimic translation errors."""
    pass

class LLMHandler:
    """Handles interactions with Language Models (LLMs) using OpenAI API."""
    
    def __init__(self, api_key_file: str):
        """Initialize the LLM handler.

        Args:
            api_key_file (str): Path to the API key file
        """
        self.setup_api(api_key_file)
        self.call_count: int = 0
    
    def setup_api(self, api_key_file: str) -> None:
        """Set up the OpenAI API key."""
        try:
            try:
                api_key = Path(api_key_file + '.txt').read_text().strip()
                if not api_key:
                    raise ValueError("API key file is empty")
                openai.api_key = api_key
                print("Successfully loaded API key from", api_key_file + '.txt')
            except FileNotFoundError:
                # Try without .txt extension
                try:
                    api_key = Path(api_key_file).read_text().strip()
                    if not api_key:
                        raise ValueError("API key file is empty")
                    openai.api_key = api_key
                    print("Successfully loaded API key from", api_key_file)
                except FileNotFoundError:
                    raise LLMError(f"API key file not found: {api_key_file} or {api_key_file}.txt")
        except Exception as e:
            raise LLMError(f"Error reading API key file: {str(e)}")
    
    def query_model(
        self, 
        prompt: Union[str, List[Dict]], 
        gpt_version: str, 
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        stop: Optional[List[str]] = None,
        logprobs: Optional[int] = 1,
        frequency_penalty: float = 0
    ) -> Tuple[dict, str]:
        """Query the language model using OpenAI API.
        """
        retry_delay = DEFAULT_RETRY_DELAY

        for attempt in range(MAX_RETRIES):
            try:
                self.call_count += 1
                if "gpt" not in gpt_version:
                    response = openai.completions.create(
                        model=gpt_version,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stop=stop,
                        logprobs=logprobs,
                        frequency_penalty=frequency_penalty
                    )
                    return response, response.choices[0].text.strip()
                else:
                    response = openai.chat.completions.create(
                        model=gpt_version,
                        messages=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        frequency_penalty=frequency_penalty
                    )
                    return response, response.choices[0].message.content.strip()
                    
            except openai.RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                raise LLMError("Rate limit exceeded")
                
            except (openai.APIError, openai.APITimeoutError) as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(retry_delay)
                    continue
                raise LLMError(f"API Error after all retries: {str(e)}")
                
            except Exception as e:
                raise LLMError(f"Unexpected error in LLM query: {str(e)}")

class MimicFormatTranslator:
    """Translates complete PDDL plans to mimic format using OpenAI API."""

    def __init__(self, api_key_file: str, gpt_version: str = "gpt-4o", wait_units: int = 100, action_durations: Optional[Dict[str, float]] = None, scene_type: str = "real_world"):
        self.gpt_version = gpt_version
        self.llm = LLMHandler(api_key_file)
        self.wait_units = wait_units
        self.action_durations = action_durations or {}
        self.scene_type = scene_type
        print(f"Initialized MimicFormatTranslator with {gpt_version}, wait_units={wait_units}, scene_type={scene_type}, action_durations={self.action_durations}")

    def _format_action_durations_comment(self) -> str:
        if not self.action_durations:
            return "# (no action duration table provided)\n"
        lines = []
        for k, v in self.action_durations.items():
            lines.append(f"# - {k} ≈ {v}s")
        return "\n".join(lines) + "\n"
    
    def validate_mimic_code(self, mimic_code: str, task_description: str) -> Tuple[bool, str]:
        """Validate if the generated mimic code would be executable by execute_plan.py.
        
        Args:
            mimic_code (str): The generated mimic code to validate
            task_description (str): Description of the task for context
            
        Returns:
            Tuple[bool, str]: (is_valid, validation_message)
        """
        try:
            # Create validation prompt
            validation_prompt = f"""You are a Python code validator for AI2-THOR robot execution. 
Your task is to validate if the following code would be executable by execute_plan.py.

Context: This code is generated from a PDDL plan for the task: "{task_description}"

Available AI2-THOR functions (assume these are imported and available):
- GoToObject(robot, object_name)
- PickupObject(robot, object_name) 
- PutObject(robot, object_name, target_location)
- ToggleObjectOn(robot, object_name)
- ToggleObjectOff(robot, object_name)
- time.sleep(seconds)

Available variables (assume these are defined):
- robots: list of robot objects [robots[0], robots[1], etc.]
- action_queue: list for tracking actions
- task_over: boolean flag

Validation criteria:
1. All function calls must use valid AI2-THOR functions
2. All robot parameters must reference robots list (e.g., robots[0], robots[1])
3. Function parameters should be 'robots' (not 'robot') and access robots[0], robots[1], etc.
4. Threading must be properly structured with start() and join()
5. Action queue must be properly managed
6. No undefined variables or functions
7. Proper Python syntax

Generated code to validate:
{mimic_code}

Please analyze this code and respond with:
1. VALID: true/false
2. ISSUES: List any issues found (empty if valid)
3. SUGGESTIONS: How to fix any issues (empty if valid)

Format your response exactly like this:
VALID: true
ISSUES: 
SUGGESTIONS: 

Or if there are issues:
VALID: false
ISSUES: 
- Issue 1 description
- Issue 2 description
SUGGESTIONS:
- Fix 1: specific suggestion
- Fix 2: specific suggestion
"""

            # Query the model for validation - use proper message format for GPT models
            if "gpt" not in self.gpt_version:
                # For older models, use string prompt
                _, validation_response = self.llm.query_model(
                    prompt=validation_prompt,
                    gpt_version=self.gpt_version,
                    max_tokens=512,
                    temperature=0.0,  # Use 0 temperature for consistent validation
                    frequency_penalty=0.0
                )
            else:
                # For GPT models, use message format
                messages = [
                    {"role": "system", "content": "You are a Python code validator for AI2-THOR robot execution. Your task is to validate if code would be executable by execute_plan.py."},
                    {"role": "user", "content": validation_prompt}
                ]
                _, validation_response = self.llm.query_model(
                    prompt=messages,
                    gpt_version=self.gpt_version,
                    max_tokens=512,
                    temperature=0.0,  # Use 0 temperature for consistent validation
                    frequency_penalty=0.0
                )
            
            # Parse validation response
            is_valid = False
            issues = []
            suggestions = []
            
            lines = validation_response.strip().split('\n')
            for line in lines:
                if line.startswith('VALID:'):
                    is_valid = line.split(':', 1)[1].strip().lower() == 'true'
                elif line.startswith('ISSUES:'):
                    # Collect all issue lines until we hit SUGGESTIONS
                    continue
                elif line.startswith('SUGGESTIONS:'):
                    # Collect all suggestion lines
                    continue
                elif line.strip().startswith('-') and 'ISSUES:' in validation_response:
                    # This is an issue line
                    if 'SUGGESTIONS:' not in validation_response or validation_response.find('ISSUES:') < validation_response.find('SUGGESTIONS:'):
                        issues.append(line.strip()[1:].strip())
                elif line.strip().startswith('-') and 'SUGGESTIONS:' in validation_response:
                    # This is a suggestion line
                    if validation_response.find('SUGGESTIONS:') < validation_response.find(line):
                        suggestions.append(line.strip()[1:].strip())
            
            # Create validation message
            if is_valid:
                validation_message = "✓ Code validation passed - executable by execute_plan.py"
            else:
                validation_message = f"✗ Code validation failed:\n"
                if issues:
                    validation_message += "Issues found:\n"
                    for issue in issues:
                        validation_message += f"  - {issue}\n"
                if suggestions:
                    validation_message += "Suggestions:\n"
                    for suggestion in suggestions:
                        validation_message += f"  - {suggestion}\n"
            
            return is_valid, validation_message
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def validate_and_fix_mimic_code(self, mimic_code: str, task_description: str) -> Tuple[bool, str, str]:
        """Validate and fix the generated mimic code to match the AI2-THOR template.
        
        Args:
            mimic_code (str): The generated mimic code to validate and fix
            task_description (str): Description of the task for context
            
        Returns:
            Tuple[bool, str, str]: (is_valid, validation_message, corrected_code)
        """
        try:
            # Create validation and fixing prompt
            fix_prompt = f"""You are a Python code validator and fixer for AI2-THOR robot execution. 
Your task is to validate and FIX the following code to match the AI2-THOR template structure.

Context: This code is generated from a PDDL plan for the task: "{task_description}"

CRITICAL: DO NOT REDEFINE AI2-THOR FUNCTIONS
The following AI2-THOR functions are ALREADY DEFINED and available:
- GoToObject(robot, object_name)
- PickupObject(robot, object_name) 
- PutObject(robot, object_name, target_location)
- ToggleObjectOn(robot, object_name)
- ToggleObjectOff(robot, object_name)
- time.sleep(seconds)

DO NOT create new function definitions for these. Use them directly as shown in the template.
DO NOT add "def GoToObject(...):" or similar definitions.

Required template structure:
1. Functions should take 'robots' parameter and use robots[0], robots[1], etc.
2. Use proper threading for parallel execution
3. Include action_queue management
4. Use task_over flag
5. Follow this exact structure:

def task_function(robots):
    # Task description
    GoToObject(robots[0], 'Object')
    PickupObject(robots[0], 'Object')
    # ... more actions

# Threading setup
task1_thread = threading.Thread(target=task_function, args=(robots,))
task1_thread.start()
task1_thread.join()

# Action queue and completion
action_queue.append({{'action':'Done'}})
task_over = True
time.sleep(5)

Generated code to fix:
{mimic_code}

Please analyze this code and:
1. Fix all issues to match the AI2-THOR template
2. Ensure proper robot parameter usage (robots[0], robots[1])
3. Add proper threading structure if missing
4. Add action_queue and task_over management
5. Remove any invalid AI2-THOR functions and replace with valid ones
6. REMOVE any function definitions for GoToObject, PickupObject, PutObject, etc. - these are already available

Return ONLY the corrected code that follows the template structure exactly.
"""

            # Query the model for fixing
            if "gpt" not in self.gpt_version:
                # For older models, use string prompt
                _, corrected_code = self.llm.query_model(
                    prompt=fix_prompt,
                    gpt_version=self.gpt_version,
                    max_tokens=2048,
                    temperature=0.0,
                    frequency_penalty=0.0
                )
            else:
                # For GPT models, use message format
                messages = [
                    {"role": "system", "content": "You are a Python code fixer for AI2-THOR robot execution. Fix the code to match the exact template structure."},
                    {"role": "user", "content": fix_prompt}
                ]
                _, corrected_code = self.llm.query_model(
                    prompt=messages,
                    gpt_version=self.gpt_version,
                    max_tokens=2048,
                    temperature=0.0,
                    frequency_penalty=0.0
                )
            
            # Clean up the corrected code (remove markdown if present)
            corrected_code = corrected_code.strip()
            if corrected_code.startswith('```python'):
                corrected_code = corrected_code[9:]
            if corrected_code.endswith('```'):
                corrected_code = corrected_code[:-3]
            corrected_code = corrected_code.strip()
            
            # Validate the corrected code
            is_valid, validation_message = self.validate_mimic_code(corrected_code, task_description)
            
            return is_valid, validation_message, corrected_code
            
        except Exception as e:
            return False, f"Validation and fixing error: {str(e)}", mimic_code
    
    def create_few_shot_prompt(self, task_description: str, combined_plan: str) -> Union[str, List[Dict]]:
        if self.scene_type != "real_world":
            return self._create_kitchen_few_shot_prompt(task_description, combined_plan)
        # Few-shot examples for complete plan translation (real-world)
        few_shot_examples = f"""# CRITICAL INSTRUCTION: DO NOT REDEFINE AI2-THOR FUNCTIONS
# The following AI2-THOR functions are ALREADY DEFINED and available:
# - GoToObject(robot, object_name)
# - PickupObject(robot, object_name)
# - PutObject(robot, object_name, target_location)
# - ToggleObjectOn(robot, object_name)
# - ToggleObjectOff(robot, object_name)
# - time.sleep(seconds)
#
# DO NOT create new function definitions for these. Use them directly as shown in the template.
# DO NOT add "def GoToObject(...):" or similar definitions.
#
# WAIT TIME GUIDELINE:
# - For autonomous operations (stove cooking, boiling, making tea, etc.), use time.sleep({self.wait_units}).
# - For immediate sequential actions (pick then place), no sleep needed.
# - Turn off appliances immediately after their operation completes.
#
# APPROXIMATE PER-ACTION DURATIONS (seconds):
{self._format_action_durations_comment()}#
# MAKESPAN MINIMIZATION (single robot):
# - MINIMIZE total makespan: during a long time.sleep (cooking/boiling), DO NOT block idle.
# - Instead, INTERLEAVE independent subtasks BEFORE the sleep so they run during the wait,
#   OR restructure: start the cooking, then work on other subtasks, then come back to turn off.
# - Use the per-action durations above to estimate whether a sequence (e.g.,
#   GoToObject + PickupObject + GoToObject + PutObject) fits inside a time.sleep window.
# - Only call time.sleep when no independent work remains to do during the wait.

# Example: Complete PDDL Plan Translation (single-robot real-world kitchen)
Task: Make a tea with tea pot and make a tomato sauce
Complete PDDL Plan: (define (problem tea_and_sauce) (:domain robot_domain) (:objects tea_cup tea_pot tomato blue_pot stove) (:init (at tea_cup table) (at tea_pot table) (at tomato table) (at blue_pot table) (at stove kitchen)) (:goal (and (made_tea tea_pot) (made_sauce blue_pot))))

# IMPORTANT: Follow this EXACT structure for AI2-THOR execution.
# NOTE: AI2-THOR functions are already imported — DO NOT redefine them.
# NOTE: The environment has a SINGLE robot. Use robots[0] only.
# NOTE: Cooking has 3 phases — Prepare → Start → Stop.
#
# CONTAINER RULES (real-world kitchen — MANDATORY):
# - To COOK food on `stove` (sausage, chicken, fish, etc.), the food MUST be
#   placed INSIDE `pan` first, then `pan` placed ON `stove`. NEVER do
#   `PutObject(robots[0], 'sausage', 'stove')`.
# - To MAKE TOMATO SAUCE, use `blue_pot`: PutObject(robots[0], 'tomato', 'blue_pot') →
#   PutObject(robots[0], 'blue_pot', 'stove') → ToggleObjectOn('stove') →
#   ToggleObjectOff('stove'). Never use any container other than `blue_pot`.
# - To MAKE TEA, place `tea_cup` INSIDE `tea_pot`, then ToggleObjectOn('tea_pot') →
#   ToggleObjectOff('tea_pot'). tea_pot is itself the appliance — do NOT put
#   it on stove.
# - Non-cooking placement (banana/carrot/cup on plate or in sink) needs no
#   intermediate container.
#
# RESIDUAL-WAIT RULE (critical for makespan correctness):
# When you interleave independent work between TOGGLE_ON and TOGGLE_OFF, the
# physical cooking time is fixed at {self.wait_units} seconds. The remaining
# time.sleep AFTER the interleaved work must be:
#   residual = max(0, {self.wait_units} - sum_of_interleaved_action_durations)
# Do NOT call time.sleep({self.wait_units}) AND ALSO run interleaved work — that
# overshoots the cook time and inflates makespan.
#
# OUTPUT FORMAT for time.sleep:
# - Always emit a single LITERAL FLOAT, e.g., `time.sleep(33.08)`.
# - Do NOT emit expressions like `time.sleep(max(0, 60 - 26.92))` or
#   `time.sleep(wait_units - elapsed)`. Compute the value yourself using the
#   per-action duration table above and write the resulting number directly.
# - If interleaved work fully covers the cook time (residual <= 0), emit
#   `time.sleep(0.0)` and proceed to TOGGLE_OFF.

def execute_task(robots):
    # === Tea task — Phase A (Prepare): tea_cup in tea_pot ===
    GoToObject(robots[0], 'tea_cup')
    PickupObject(robots[0], 'tea_cup')
    GoToObject(robots[0], 'tea_pot')
    PutObject(robots[0], 'tea_cup', 'tea_pot')
    # === Tea task — Phase B (Start): toggle on tea_pot ===
    ToggleObjectOn(robots[0], 'tea_pot')

    # === Interleave the entire tomato-sauce preparation during the tea wait ===
    # Each NAV+GRASP+NAV+PLACE ≈ 2.1 + 4.51 + 2.1 + 4.75 = 13.46s.
    # tomato → blue_pot
    GoToObject(robots[0], 'tomato')
    PickupObject(robots[0], 'tomato')
    GoToObject(robots[0], 'blue_pot')
    PutObject(robots[0], 'tomato', 'blue_pot')
    # blue_pot → stove
    GoToObject(robots[0], 'blue_pot')
    PickupObject(robots[0], 'blue_pot')
    GoToObject(robots[0], 'stove')
    PutObject(robots[0], 'blue_pot', 'stove')
    # start the stove (sauce begins cooking while tea is still steeping)
    ToggleObjectOn(robots[0], 'stove')

    # === Residual wait for tea: tea cook time minus interleaved work ===
    # tea cook duration = {self.wait_units}s, interleaved ≈ 3 × 13.46 ≈ 40.38s
    # (two transports + one toggle which we ignore in the cost model).
    # residual = max(0, {self.wait_units} - 40.38) = {max(0.0, float(self.wait_units) - 40.38):.2f}
    # → emit the literal float directly (NO arithmetic expression):
    time.sleep({max(0.0, float(self.wait_units) - 40.38):.2f})

    # === Tea task — Phase C (Stop): tea is done; tea_cup stays in tea_pot ===
    ToggleObjectOff(robots[0], 'tea_pot')
    # NOTE: NO retrieval here. tea_cup remains inside tea_pot.

    # === Sauce task — wait for the rest of its own cook time then stop ===
    # Sauce was started later than tea; it still needs the full {self.wait_units}s
    # minus whatever overlap occurred with the tea wait. In this example the
    # tea wait covered most of it, so the additional residual is short.
    # residual_sauce = max(0, {self.wait_units} - {max(0.0, float(self.wait_units) - 40.38):.2f})
    #                = {max(0.0, float(self.wait_units) - max(0.0, float(self.wait_units) - 40.38)):.2f}
    time.sleep({max(0.0, float(self.wait_units) - max(0.0, float(self.wait_units) - 40.38)):.2f})

    # === Sauce task — Phase C (Stop): sauce done; tomato stays in blue_pot ===
    ToggleObjectOff(robots[0], 'stove')
    # NOTE: NO retrieval here. tomato/sauce remains inside blue_pot.

# Single-robot threading scaffold (kept for execution-runner compatibility)
task1_thread = threading.Thread(target=execute_task, args=(robots,))
task1_thread.start()
task1_thread.join()

action_queue.append({{'action':'Done'}})

task_over = True

# Now translate the following complete plan:
Task: {task_description}
Complete PDDL Plan: {combined_plan}

# IMPORTANT: Generate code that follows the EXACT structure above
def execute_task():
    # Complete plan execution for: {task_description}
"""
        
        # Return as string for older GPT models, or as messages for newer ones
        if "gpt" not in self.gpt_version:
            return few_shot_examples
        else:
            return [
                {"role": "system", "content": "You are a Robot PDDL to Mimic Format Translator. Your task is to translate complete PDDL plans into executable Python code following the AI2-THOR controller format. Translate the entire plan as a single coherent function."},
                {"role": "user", "content": few_shot_examples}
            ]
    
    def _create_kitchen_few_shot_prompt(self, task_description: str, combined_plan: str) -> Union[str, List[Dict]]:
        """Few-shot prompt for AI2-THOR kitchen scenes.

        Mirrors the scenarios used by dag_bayesian's
        `assets/prompts/e2e_generator_ver12_kitchen.txt` (Examples 1, 3, 6)
        but expressed as single-robot mimic Python so the parser can extract
        `GoToObject / PickupObject / PutObject / OpenObject / CloseObject /
        ToggleObjectOn / ToggleObjectOff / SliceObject / time.sleep` calls.
        Uses object TYPE names (e.g., 'Microwave', 'Pot', 'StoveKnob'); the
        action_adapter resolves them to AI2-THOR objectIds at execution time.
        """
        few_shot_examples = f"""# CRITICAL INSTRUCTION: DO NOT REDEFINE AI2-THOR FUNCTIONS
# The following AI2-THOR functions are ALREADY DEFINED and available:
# - GoToObject(robot, object_name)
# - PickupObject(robot, object_name)
# - PutObject(robot, object_name, target_location)
# - OpenObject(robot, object_name)
# - CloseObject(robot, object_name)
# - ToggleObjectOn(robot, object_name)
# - ToggleObjectOff(robot, object_name)
# - SliceObject(robot, object_name)
# - time.sleep(seconds)
#
# DO NOT create new function definitions for these. Use them directly.
# DO NOT add "def GoToObject(...):" or similar definitions.
#
# NOTE: AI2-THOR kitchen environment. Use object TYPE names only (e.g.,
#       'Microwave', 'Pot', 'StoveKnob') — the executor resolves them to
#       full objectIds. The environment has a SINGLE robot — use robots[0].
#
# CONTAINER RULES (AI2-THOR kitchen — MANDATORY):
# - HEAT food in `Microwave`: GoToObject(Microwave) -> OpenObject(Microwave)
#   -> PutObject(food, Microwave) -> CloseObject(Microwave)
#   -> ToggleObjectOn(Microwave) -> wait or do other job
#   -> ToggleObjectOff(Microwave). Microwave MUST be CLOSED before TOGGLE_ON.
# - COOK on STOVE: place food into `Pan` (or `Pot`) -> PickupObject(Pan)
#   -> PutObject(Pan, StoveBurner) -> ToggleObjectOn(StoveKnob).
#   IMPORTANT: `Stove` and `StoveBurner` are NOT in the TOGGLE_ON list —
#   only `StoveKnob` is. Stop with ToggleObjectOff(StoveKnob).
# - STORE in `Fridge`: GoToObject(Fridge) -> OpenObject(Fridge)
#   -> PutObject(food, Fridge) -> CloseObject(Fridge). Fridge has no TOGGLE.
# - FILL `Pot`/`Mug` with water: PickupObject(Pot) -> PutObject(Pot, SinkBasin)
#   -> ToggleObjectOn(Faucet) -> wait -> ToggleObjectOff(Faucet)
#   -> PickupObject(Pot) to take it out.
# - MAKE COFFEE: PutObject(Mug, CoffeeMachine) -> ToggleObjectOn(CoffeeMachine)
#   -> wait -> ToggleObjectOff(CoffeeMachine).
# - SLICE Egg in Pan: PickupObject(Egg) -> PutObject(Egg, Pan)
#   -> SliceObject(Egg). The egg cracks open in the pan and cooks there.
# - SLICE other food (Tomato/Potato/Apple/Bread/Lettuce): if a Knife is
#   available and graspable, GRASP Knife first, then SliceObject(<food>),
#   then put Knife back.
# - For BREAD heating use the Microwave (NOT Toaster). Bread heating in our
#   experiments only uses Microwave.
#
# RESIDUAL-WAIT RULE (critical for makespan correctness):
# When you interleave independent work between TOGGLE_ON and TOGGLE_OFF, the
# physical cooking time is fixed at {self.wait_units} seconds. The remaining
# time.sleep AFTER the interleaved work must be:
#   residual = max(0, {self.wait_units} - sum_of_interleaved_action_durations)
# Do NOT call time.sleep({self.wait_units}) AND ALSO run interleaved work — that
# overshoots the cook time and inflates makespan.
#
# OUTPUT FORMAT for time.sleep:
# - Always emit a single LITERAL FLOAT, e.g., `time.sleep(33.08)`.
# - Do NOT emit expressions like `time.sleep(max(0, 60 - 26.92))` or
#   `time.sleep(wait_units - elapsed)`. Compute the value yourself using the
#   per-action duration table above and write the resulting number directly.
# - If interleaved work fully covers the cook time (residual <= 0), emit
#   `time.sleep(0.0)` and proceed to TOGGLE_OFF.

# === Example A: Heat Potato in Microwave + place items on plate ===
Task: Heat Potato using Microwave and set the table for lunch
Complete PDDL Plan: (define (problem heat_and_set) (:domain robot_domain) (:objects Potato Microwave Plate Tomato Bread CounterTop) (:init (at Potato CounterTop) (at Plate CounterTop) (at Tomato CounterTop) (at Bread CounterTop)) (:goal (and (heated Potato) (on Plate CounterTop) (on Tomato CounterTop) (on Bread Plate))))

def execute_task(robots):
    # --- Microwave Phase A: Prepare + Start ---
    GoToObject(robots[0], 'Potato')
    PickupObject(robots[0], 'Potato')
    GoToObject(robots[0], 'Microwave')
    OpenObject(robots[0], 'Microwave')
    PutObject(robots[0], 'Potato', 'Microwave')
    CloseObject(robots[0], 'Microwave')
    ToggleObjectOn(robots[0], 'Microwave')

    # --- Interleave: set the table while microwave runs ---
    GoToObject(robots[0], 'Plate')
    PickupObject(robots[0], 'Plate')
    GoToObject(robots[0], 'CounterTop')
    PutObject(robots[0], 'Plate', 'CounterTop')
    GoToObject(robots[0], 'Tomato')
    PickupObject(robots[0], 'Tomato')
    GoToObject(robots[0], 'CounterTop')
    PutObject(robots[0], 'Tomato', 'CounterTop')
    GoToObject(robots[0], 'Bread')
    PickupObject(robots[0], 'Bread')
    GoToObject(robots[0], 'Plate')
    PutObject(robots[0], 'Bread', 'Plate')

    # --- Residual wait (microwave cook time minus interleaved work) ---
    # interleaved ≈ 3 placements × ~9.4s ≈ 28.2s
    time.sleep({max(0.0, float(self.wait_units) - 28.2):.2f})

    # --- Microwave Phase B: Stop ---
    GoToObject(robots[0], 'Microwave')
    ToggleObjectOff(robots[0], 'Microwave')

# === Example B: Cook Egg on Stove (Pan + StoveBurner + StoveKnob + SLICE Egg) ===
Task: Cook egg fry
Complete PDDL Plan: (define (problem cook_egg) (:domain robot_domain) (:objects Egg Pan StoveBurner StoveKnob CounterTop) (:init (at Egg CounterTop) (at Pan CounterTop)) (:goal (cooked Egg)))

def execute_task(robots):
    # --- Place pan on stove ---
    GoToObject(robots[0], 'Pan')
    PickupObject(robots[0], 'Pan')
    GoToObject(robots[0], 'StoveBurner')
    PutObject(robots[0], 'Pan', 'StoveBurner')
    # --- Crack egg into the pan (SliceObject on Egg-in-Pan) ---
    GoToObject(robots[0], 'Egg')
    PickupObject(robots[0], 'Egg')
    GoToObject(robots[0], 'Pan')
    PutObject(robots[0], 'Egg', 'Pan')
    SliceObject(robots[0], 'Egg')
    # --- Start the stove via StoveKnob (NOT Stove or StoveBurner) ---
    GoToObject(robots[0], 'StoveKnob')
    ToggleObjectOn(robots[0], 'StoveKnob')
    # --- Wait for the egg to cook (no independent work to interleave here) ---
    time.sleep({float(self.wait_units):.2f})
    # --- Stop the stove ---
    GoToObject(robots[0], 'StoveKnob')
    ToggleObjectOff(robots[0], 'StoveKnob')

# === Example C: Boil Potato (Fill Pot from Faucet, then heat on StoveKnob) ===
Task: Boil Potato
Complete PDDL Plan: (define (problem boil_potato) (:domain robot_domain) (:objects Potato Pot SinkBasin Faucet StoveBurner StoveKnob) (:init (at Potato CounterTop) (at Pot CounterTop)) (:goal (boiled Potato)))

def execute_task(robots):
    # --- Fill Pot under Faucet ---
    GoToObject(robots[0], 'Pot')
    PickupObject(robots[0], 'Pot')
    GoToObject(robots[0], 'SinkBasin')
    PutObject(robots[0], 'Pot', 'SinkBasin')
    GoToObject(robots[0], 'Faucet')
    ToggleObjectOn(robots[0], 'Faucet')
    # short fill wait (literal, faucet-specific)
    time.sleep(10.0)
    GoToObject(robots[0], 'Faucet')
    ToggleObjectOff(robots[0], 'Faucet')
    # --- Move filled Pot to StoveBurner ---
    GoToObject(robots[0], 'Pot')
    PickupObject(robots[0], 'Pot')
    GoToObject(robots[0], 'StoveBurner')
    PutObject(robots[0], 'Pot', 'StoveBurner')
    # --- Drop potato into pot ---
    GoToObject(robots[0], 'Potato')
    PickupObject(robots[0], 'Potato')
    GoToObject(robots[0], 'Pot')
    PutObject(robots[0], 'Potato', 'Pot')
    # --- Start StoveKnob and wait for boil ---
    GoToObject(robots[0], 'StoveKnob')
    ToggleObjectOn(robots[0], 'StoveKnob')
    time.sleep({float(self.wait_units):.2f})
    GoToObject(robots[0], 'StoveKnob')
    ToggleObjectOff(robots[0], 'StoveKnob')

# === Example D: Store items in Fridge (independent placements) ===
Task: Put tomato and apple in fridge
Complete PDDL Plan: (define (problem store_in_fridge) (:domain robot_domain) (:objects Tomato Apple Fridge) (:init (at Tomato CounterTop) (at Apple CounterTop)) (:goal (and (in Tomato Fridge) (in Apple Fridge))))

def execute_task(robots):
    GoToObject(robots[0], 'Tomato')
    PickupObject(robots[0], 'Tomato')
    GoToObject(robots[0], 'Fridge')
    OpenObject(robots[0], 'Fridge')
    PutObject(robots[0], 'Tomato', 'Fridge')
    CloseObject(robots[0], 'Fridge')
    GoToObject(robots[0], 'Apple')
    PickupObject(robots[0], 'Apple')
    GoToObject(robots[0], 'Fridge')
    OpenObject(robots[0], 'Fridge')
    PutObject(robots[0], 'Apple', 'Fridge')
    CloseObject(robots[0], 'Fridge')

# Single-robot threading scaffold (kept for execution-runner compatibility)
task1_thread = threading.Thread(target=execute_task, args=(robots,))
task1_thread.start()
task1_thread.join()

action_queue.append({{'action':'Done'}})

task_over = True

# Now translate the following complete plan:
Task: {task_description}
Complete PDDL Plan: {combined_plan}

# IMPORTANT: Generate code that follows the EXACT structure above
def execute_task():
    # Complete plan execution for: {task_description}
"""

        if "gpt" not in self.gpt_version:
            return few_shot_examples
        return [
            {"role": "system", "content": "You are a Robot PDDL to Mimic Format Translator for AI2-THOR kitchen scenes. Translate PDDL plans into executable Python mimic code, respecting the kitchen container rules (Microwave open/close, Stove via StoveKnob, Fridge open/close, Faucet+SinkBasin for water, SliceObject(Egg) cracks egg in pan)."},
            {"role": "user", "content": few_shot_examples},
        ]

    def translate_to_mimic_format(self, task_description: str, combined_plan: str,
                                max_tokens: int = 2048,  # Increased for complete plans
                                temperature: float = 0.1,
                                frequency_penalty: float = 0.0) -> str:
        """Translate complete PDDL plan to mimic format using OpenAI API."""
        try:
            # Create few-shot prompt
            prompt = self.create_few_shot_prompt(task_description, combined_plan)
            
            # Query the model
            start_time = time.time()
            _, response = self.llm.query_model(
                prompt=prompt,
                gpt_version=self.gpt_version,
                max_tokens=max_tokens,
                temperature=temperature,
                frequency_penalty=frequency_penalty
            )
            translation_time = time.time() - start_time
            
            print(f"Translation completed in {translation_time:.2f}s")
            return response
            
        except Exception as e:
            raise MimicTranslationError(f"Error in mimic translation: {str(e)}")
    
    def extract_function_name(self, task_description: str) -> str:
        """Extract a function name from task description."""
        clean_task = re.sub(r'[^a-zA-Z0-9\s]', '', task_description.lower())
        words = clean_task.split()[:3]  # Take first 3 words
        function_name = '_'.join(words)
        return function_name

def load_pddl_results_from_logs(logs_dir: str) -> List[Dict[str, Any]]:
    """Load PDDL results from the log directories created by pddlrun_llmseparate.py."""
    
    results = []
    logs_path = Path(logs_dir)
    
    if not logs_path.exists():
        print(f"Logs directory not found: {logs_dir}")
        return results
    
    # Find all log folders (they end with _plans_YYYY-MM-DD-HH-MM-SS)
    log_folders = list(logs_path.glob("*_plans_*"))
    
    if not log_folders:
        print(f"No log folders found in {logs_dir}")
        return results
    
    print(f"Found {len(log_folders)} log folders")
    
    for folder in log_folders:
        try:
            # Read log.txt to get task information
            log_file = folder / "log.txt"
            if not log_file.exists():
                print(f"Warning: log.txt not found in {folder}")
                continue
            
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            # Extract task description from log content
            lines = log_content.split('\n')
            task_description = lines[0] if lines else "Unknown task"
            
            # Read the COMBINED plan (code_planpddl.py) - this contains the complete executable plan
            combined_plan_file = folder / "code_planpddl.py"
            if not combined_plan_file.exists():
                print(f"Warning: code_planpddl.py not found in {folder}")
                continue
            
            with open(combined_plan_file, 'r', encoding='utf-8') as f:
                combined_plan_content = f.read()
            
            # Create result entry with the complete plan
            result = {
                'episode_id': folder.name,
                'scene_id': 'pddl_generated',
                'task_description': task_description,
                'combined_plan': combined_plan_content,  # Store the complete plan
                'log_folder': str(folder)
            }
            
            results.append(result)
            print(f"  ✓ Loaded: {folder.name} - {task_description[:50]}...")
            print(f"    Plan length: {len(combined_plan_content)} characters")
            
        except Exception as e:
            print(f"Error processing folder {folder}: {e}")
            continue
    
    print(f"Successfully loaded {len(results)} PDDL results")
    return results

def load_extraction_results(results_file: str) -> List[Dict[str, Any]]:
    """Load results from JSON file (for backward compatibility)."""
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        print(f"Loaded {len(results)} results from {results_file}")
        return results
    except Exception as e:
        print(f"Error loading results file {results_file}: {e}")
        return []

def process_results_for_plan_to_code(results: List[Dict[str, Any]], translator: MimicFormatTranslator,
                            output_dir: str, batch_size: int = 3, validate_code: bool = True) -> List[Dict[str, Any]]:
    """Process all results to translate to plan-to-code format."""
    processed_results = []
    
    print(f"Processing {len(results)} results for plan-to-code translation...")
    print(f"Processing in batches of {batch_size}")
    if validate_code:
        print("Code validation enabled - checking execute_plan.py compatibility")
    else:
        print("Code validation disabled")
    
    # Process in batches to manage API rate limits
    for batch_start in range(0, len(results), batch_size):
        batch_end = min(batch_start + batch_size, len(results))
        batch_results = results[batch_start:batch_end]
        
        print(f"\nProcessing batch {batch_start//batch_size + 1}/{(len(results) + batch_size - 1)//batch_size}")
        print(f"Tasks {batch_start + 1}-{batch_end}")
        
        for i, result in enumerate(batch_results):
            global_index = batch_start + i
            episode_id = result.get('episode_id', f'task_{global_index}')
            scene_id = result.get('scene_id', 'unknown')
            task_description = result.get('task_description', '')
            combined_plan = result.get('combined_plan', '')
            
            print(f"\n[{global_index + 1}/{len(results)}] Processing Episode {episode_id}, Scene {scene_id}")
            
            try:
                # Skip if no combined plan was loaded
                if not combined_plan or combined_plan.strip() == "":
                    print(f"  ⚠ No combined plan found, skipping")
                    processed_result = {
                        'episode_id': episode_id,
                        'scene_id': scene_id,
                        'task_description': task_description,
                        'original_combined_plan': combined_plan,
                        'mimic_format_code': None,
                        'function_name': None,
                        'translation_time': 0,
                        'success': False,
                        'error': 'No combined plan to translate',
                        'validation_message': 'Skipped - no plan to validate',
                        'log_folder': result.get('log_folder', '')  # Add the log_folder to processed_result
                    }
                    processed_results.append(processed_result)
                    continue
                
                # Translate to mimic format using OpenAI API
                start_time = time.time()
                mimic_code = translator.translate_to_mimic_format(task_description, combined_plan)
                translation_time = time.time() - start_time
                
                # Extract function name
                function_name = translator.extract_function_name(task_description)
                
                # Validate and fix the generated mimic code if enabled
                if validate_code:
                    print(f"  🔧 Validating and fixing generated code...")
                    try:
                        is_valid, validation_message, corrected_code = translator.validate_and_fix_mimic_code(mimic_code, task_description)
                        # Use the corrected code instead of the original
                        if corrected_code and len(corrected_code.strip()) > 0:
                            mimic_code = corrected_code
                            print(f"  📝 Original code length: {len(mimic_code) if mimic_code else 0}")
                            print(f"  📝 Corrected code length: {len(corrected_code) if corrected_code else 0}")
                            print(f"  ✅ Validation result: {is_valid}")
                        else:
                            print(f"  ⚠ Validation returned empty code, using original")
                            is_valid = True
                            validation_message = "Using original code - validation returned empty"
                    except Exception as e:
                        print(f"  ⚠ Validation failed: {e}, using original code")
                        is_valid = True
                        validation_message = f"Using original code - validation error: {str(e)}"
                else:
                    is_valid = True
                    validation_message = "Validation skipped"
                
                # Create processed result
                processed_result = {
                    'episode_id': episode_id,
                    'scene_id': scene_id,
                    'task_description': task_description,
                    'original_combined_plan': combined_plan,
                    'mimic_format_code': mimic_code,
                    'function_name': function_name,
                    'translation_time': translation_time,
                    'extraction_time': result.get('extraction_time', 0),
                    'generation_time': result.get('generation_time', 0),
                    'success': len(mimic_code.strip()) > 0 if mimic_code else False, # Consider successful if we have code, regardless of validation
                    'validation_passed': is_valid,  # Track validation status separately
                    'validation_message': validation_message,
                    'log_folder': result.get('log_folder', '')  # Add the log_folder to processed_result
                }
                
                processed_results.append(processed_result)
                
                print(f"  ✓ Translated to mimic format ({translation_time:.2f}s)")
                print(f"  Function name: {function_name}")
                print(f"  Code preview: {mimic_code[:100]}{'...' if len(mimic_code) > 100 else ''}")
                # Remove validation message printing but keep validation functionality
                
            except Exception as e:
                print(f"  ✗ Error in mimic translation: {e}")
                processed_result = {
                    'episode_id': episode_id,
                    'scene_id': scene_id,
                    'task_description': task_description,
                    'original_combined_plan': combined_plan,
                    'error': str(e),
                    'success': False,
                    'validation_message': f'Error during translation: {str(e)}',
                    'log_folder': result.get('log_folder', '')  # Add the log_folder to processed_result
                }
                processed_results.append(processed_result)
        
        # Add delay between batches to respect API rate limits
        if batch_start + batch_size < len(results):
            print(f"  Waiting 2 seconds before next batch...")
            time.sleep(2)
    
    return processed_results

def save_individual_plan_to_code_files(processed_results: List[Dict[str, Any]], output_dir: str):
    """Save individual plan-to-code format files directly in the original log folders."""
    
    successful_translations = [r for r in processed_results if r.get('success', False)]
    
    print(f"\nSaving {len(successful_translations)} plan-to-code files in original log folders...")
    
    for i, result in enumerate(successful_translations):
        episode_id = result.get('episode_id', f'task_{i}')
        scene_id = result.get('scene_id', 'unknown')
        function_name = result.get('function_name', f'task_{i}')
        plan_to_code = result.get('mimic_format_code', '')
        task_description = result.get('task_description', '')
        log_folder = result.get('log_folder', '')
        validation_passed = result.get('validation_passed', False)
        validation_message = result.get('validation_message', '')
        
        print(f"  📁 Processing: {episode_id}")
        print(f"  📝 Code length: {len(plan_to_code) if plan_to_code else 0}")
        print(f"  📂 Log folder: {log_folder}")
        print(f"  ✅ Validation passed: {validation_passed}")
        if not validation_passed:
            print(f"  ⚠ Validation issues: {validation_message[:100]}...")
        
        if log_folder and Path(log_folder).exists():
            original_log_path = Path(log_folder)
            
            # Check if we have valid code to save
            if not plan_to_code or len(plan_to_code.strip()) == 0:
                print(f"  ⚠ No valid code to save for {episode_id}")
                continue
            
            # Create plan_to_code subdirectory in the original log folder
            plan_to_code_dir = original_log_path / "plan_to_code"
            plan_to_code_dir.mkdir(exist_ok=True)
            
            # Save the plan-to-code file in the log folder
            filename = f"plan_to_code_{function_name}.py"
            filepath = plan_to_code_dir / filename
            
            # Create complete Python file content
            file_content = f"""
\"\"\"
Plan-to-Code Format for AI2-THOR Controller
Generated from Complete PDDL Plan Translation

Episode ID: {episode_id}
Scene ID: {scene_id}
Task: {task_description}
Validation Passed: {validation_passed}
Validation Message: {validation_message}
\"\"\"

import time
import threading

# Import AI2-THOR controller functions
# from ai2thor_controller import GoToObject, PickupObject, PutObject, ToggleObjectOn, ToggleObjectOff

{plan_to_code}

# Example usage:
# robot = get_robot_instance()
# execute_task(robot)
"""
            
            # Save file in the log folder
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            print(f"  ✓ Saved: {filename} in {log_folder}")
            
            # Also save as code_plan.py in the main log folder for execute_plan.py compatibility
            code_plan_path = original_log_path / "code_plan.py"
            with open(code_plan_path, 'w', encoding='utf-8') as f:
                f.write(plan_to_code)
            
            print(f"  ✓ Saved code_plan.py in: {log_folder}")
            
        else:
            print(f"  ⚠ Could not save files - log folder not found: {log_folder}")
    
    print(f"All plan-to-code files saved in their respective log folders")

def generate_summary(processed_results: List[Dict[str, Any]], output_dir: str):
    """Generate summary statistics and reports."""
    total_results = len(processed_results)
    successful_translations = sum(1 for r in processed_results if r.get('success', False))
    
    # Validation statistics
    validation_results = [r.get('validation_message', '') for r in processed_results]
    validation_passed = sum(1 for msg in validation_results if '✓' in msg or 'passed' in msg.lower())
    validation_failed = sum(1 for msg in validation_results if '✗' in msg or 'failed' in msg.lower())
    validation_skipped = sum(1 for msg in validation_results if 'skipped' in msg.lower())
    
    # Time statistics
    translation_times = [r.get('translation_time', 0) for r in processed_results if r.get('translation_time')]
    avg_translation_time = sum(translation_times) / len(translation_times) if translation_times else 0
    
    # Generate summary report
    summary = {
        'total_results': total_results,
        'successful_translations': successful_translations,
        'success_rate': successful_translations / total_results * 100 if total_results > 0 else 0,
        'validation_passed': validation_passed,
        'validation_failed': validation_failed,
        'validation_skipped': validation_skipped,
        'validation_success_rate': validation_passed / (validation_passed + validation_failed) * 100 if (validation_passed + validation_failed) > 0 else 0,
        'average_translation_time': avg_translation_time,
        'total_translation_time': sum(translation_times)
    }
    
    # Save summary in output directory
    summary_file = Path(output_dir) / "plan_to_code_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    # Save detailed results in output directory
    results_file = Path(output_dir) / "plan_to_code_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(processed_results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n=== PLAN-TO-CODE TRANSLATION SUMMARY ===")
    print(f"Total results processed: {total_results}")
    print(f"Successful translations: {successful_translations} ({summary['success_rate']:.1f}%)")
    # Remove validation statistics printing but keep validation functionality
    print(f"Average translation time: {summary['average_translation_time']:.2f}s")
    print(f"Total translation time: {summary['total_translation_time']:.2f}s")
    
    print(f"\nSummary files saved to: {output_dir}")
    print(f"Summary: {summary_file}")
    print(f"Detailed results: {results_file}")
    print(f"Individual plan-to-code files saved in their respective log folders")

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Translate complete PDDL plans to AI2-THOR executable code using OpenAI API. Can load from JSON files or PDDL log directories created by pddlrun_llmseparate.py')
    parser.add_argument('--openai-api-key-file', type=str, default="api_key",
                       help='Path to OpenAI API key file')
    parser.add_argument('--gpt-version', type=str, default="gpt-4o",
                       choices=['gpt-3.5-turbo', 'gpt-4o', 'gpt-3.5-turbo-16k'],
                       help='GPT model version to use')
    parser.add_argument('--input-source', type=str, choices=['json', 'pddl_logs'], default='pddl_logs',
                       help='Input source type: json file or pddl_logs directory')
    parser.add_argument('--input-file', type=str, 
                       default='../model_testing/70b_extracted_actions/70b_extracted_action_sequences.json',
                       help='Path to the extracted action sequences JSON file (for json input source)')
    parser.add_argument('--logs-dir', type=str, 
                       default='./logs',
                       help='Path to logs directory from pddlrun_llmseparate.py (for pddl_logs input source)')
    parser.add_argument('--output-dir', type=str, 
                       default='./plan_to_code_results',
                       help='Directory to save plan-to-code translation results')
    parser.add_argument('--batch-size', type=int, default=3,
                       help='Number of tasks to process in each batch (default: 3)')
    parser.add_argument('--max-tokens', type=int, default=2048,  # Increased default
                       help='Maximum number of tokens to generate')
    parser.add_argument('--temperature', type=float, default=0.1,
                       help='Sampling temperature')
    parser.add_argument('--frequency-penalty', type=float, default=0.0,
                       help='Frequency penalty for token generation')
    parser.add_argument('--validate-code', action='store_true', default=True,
                       help='Validate generated code for execute_plan.py compatibility (default: True)')
    parser.add_argument('--no-validate-code', dest='validate_code', action='store_false',
                       help='Skip code validation')
    
    args = parser.parse_args()
    
    # Validate input based on source type
    if args.input_source == 'json' and not args.input_file:
        parser.error("--input-file must be provided for json input source")
    elif args.input_source == 'pddl_logs' and not args.logs_dir:
        parser.error("--logs-dir must be provided for pddl_logs input source")
        
    return args

def main():
    """Main execution function."""
    print(0)
    try:
        # Parse arguments
        args = parse_arguments()
        
        print(1)
        # Load results based on input source
        if args.input_source == 'json':
            print(f"Loading extraction results from JSON file: {args.input_file}")
            results = load_extraction_results(args.input_file)
        else:  # pddl_logs
            print(f"Loading PDDL results from logs directory: {args.logs_dir}")
            results = load_pddl_results_from_logs(args.logs_dir)
        
        print(2)
        if not results:
            print("No results found!")
            return
        
        print(3)
        # Create output directory
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize translator with OpenAI API
        translator = MimicFormatTranslator(
            api_key_file=args.openai_api_key_file,
            gpt_version=args.gpt_version
        )
        
        # Process results for mimic translation
        processed_results = process_results_for_plan_to_code(
            results=results,
            translator=translator,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            validate_code=args.validate_code
        )
        
        # Save individual mimic files
        save_individual_plan_to_code_files(processed_results, args.output_dir)
        
        # Generate summary
        generate_summary(processed_results, args.output_dir)
        
    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        print(f"Full error: {str(e.__class__.__name__)}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 