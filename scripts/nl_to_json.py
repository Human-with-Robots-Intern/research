import unittest
from pathlib import Path
import json
from src.utils.task.task_generator import TaskGenerator
from src.utils.config.constants import ASSETS_PATH, SCRIPTS_PATH
from src.utils.task.task_util import TaskUtil
from src.utils.common import create_module_logger

logger = create_module_logger(__name__, module_log=True)

def load_instructions_from_json(scene_name: str) -> list[str]:
    """
    Load instructions for a given scene from JSON files.
    Args:
        scene_name: Name of the scene (e.g., "FloorPlan1", "FloorPlan401")
        script_dir: Directory where the script is located
        
    Returns:
        List of instruction strings for the scene
    """
    number = int(scene_name.lstrip("FloorPlan"))
    if number >= 400:
        base_file = "bathroom_scene.json"
    elif number >= 300:
        base_file = "real_world_scene.json"
    else:
        base_file = "kitchen_scene.json"
    
    instructions = []
    
    # Load base instructions
    base_path = ASSETS_PATH / "tasks" / "nl_instructions" / base_file
    try:
        with base_path.open("r", encoding="utf-8") as f:
            base_data = json.load(f)
            instructions.extend(base_data["instructions"])
    except Exception as e:
        logger.error(f"Failed to load base instructions from {base_path}: {e}")
    
    # Load scene-specific instructions
    scene_path = ASSETS_PATH / "tasks" / "nl_instructions" / f"{scene_name}.json"
    try:
        with scene_path.open("r", encoding="utf-8") as f:
            scene_data = json.load(f)
            instructions.extend(scene_data["instructions"])
    except Exception as e:
        logger.warning(f"Failed to load scene-specific instructions from {scene_path}: {e}")
    
    return instructions

def main() -> None:
    """
    Processes natural language instructions from JSON files to generate tasks for specified scenes.
    The script reads instructions from appropriate JSON files based on scene type:
    - Kitchen scenes (FloorPlan1, FloorPlan7, etc.): kitchen_scene.json + scene-specific files
    - Bathroom scenes (FloorPlan401, etc.): bathroom_scene.json + scene-specific files
    
    For each scene, it generates tasks based on these instructions and saves the output 
    as JSON files in a scene-specific subdirectory within 'scripts/json_produced/'. 
    It also logs the subtasks and constraints derived from the generated task data.
    """
    logger = create_module_logger(__name__, module_log=True)
    
    # Define scene lists by type
    kitchen_scenes = ["FloorPlan1", "FloorPlan18"]
    bathroom_scenes = ["FloorPlan419"]
    real_world_scenes = ["FloorPlan301"]
    
    # Combine all scenes
    scene_name_list =  real_world_scenes
    
    is_rag = False
    
    # Get script directory for path resolution
    
    for scene_name in scene_name_list:
        logger.info(f"Processing scene: {scene_name}")
        
        # Load instructions for this specific scene
        instructions = load_instructions_from_json(scene_name)
        
        if not instructions:
            logger.info(f"No instructions found for scene {scene_name}")
            continue
        # Create output directory for this scene
        output_dir = SCRIPTS_PATH / "json_produced" / scene_name
        output_dir.mkdir(parents=True, exist_ok=True)
        for instruction in instructions:
            logger.info(f"Processing instruction for {scene_name}: {instruction}")
            result = TaskGenerator(is_rag, is_test=True).generate_task(instruction, scene_name)
            
            # Save result as JSON file
            output_file = output_dir / f"{instruction}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Saved result to {output_file}")
            logger.info("-" * 20)  # Separator between results
            
            # Generate subtasks and constraints
            subtasks, constraints = TaskUtil.build_tasks_and_constraints(
                task_data=result,
                scene_file_name=f"{scene_name}_physics_environment.json",
                enable_decomposition=True
            )
            logger.info(f"Subtasks for {scene_name} - {instruction}: {subtasks}")
            logger.info(f"Constraints for {scene_name} - {instruction}: {constraints}")
            logger.info("=" * 40)  # Separator between instructions
        
        logger.info(f"Finished processing scene: {scene_name}")
        logger.info("#" * 50)  # Separator between scenes
if __name__ == '__main__':
    main()
