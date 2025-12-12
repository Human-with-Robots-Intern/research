import os
import shutil
import re
from pathlib import Path

def extract_failed_tasks():
    # Configuration
    report_path = "failure_analysis_report.txt"
    source_root = Path("assets/tasks/sampled_10_instruction_set_for_final_experiment_251203")
    target_root = Path("assets/tasks/failed_cases_only")
    
    if not os.path.exists(report_path):
        print(f"Error: Report file {report_path} not found. Run analyze_failures.py first.")
        return

    print(f"Reading failure report from {report_path}...")
    
    # Parse unique failed cases: (difficulty, instruction, scene)
    # Since tasks files are organized by Scene, we should extract Scene too if possible.
    # But if we want ALL scenes for a failed task type, we can ignore scene.
    # However, failures are specific to scenes. Let's try to copy specific failed scene files first.
    # If the user wants the "Task Type" regardless of scene, we can do that too.
    # Based on the user query "실패한 case의 task만 모아줄 수 있어?", it implies specific cases.
    
    failed_cases = set()
    
    with open(report_path, "r") as f:
        content = f.read()
        
    current_diff = None
    current_instr = None
    current_scene = None
    
    for line in content.splitlines():
        if line.startswith("Difficulty: "):
            current_diff = line.split(": ")[1].strip()
        elif line.startswith("Instruction: "):
            current_instr = line.split(": ")[1].strip()
        elif line.startswith("Scene: "):
            current_scene = line.split(": ")[1].strip()
            
            if current_diff and current_instr and current_scene:
                failed_cases.add((current_diff, current_instr, current_scene))
                # Don't reset diff/instr yet, next scene might use them? 
                # Actually report format repeats Difficulty/Instruction for each file block.
                # So we are good.
    
    print(f"Found {len(failed_cases)} unique failed cases (Diff + Instr + Scene).")
    
    # 2. Copy files
    if target_root.exists():
        print(f"Cleaning existing target directory: {target_root}")
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True)
    
    copied_count = 0
    
    for diff, instr, scene in failed_cases:
        # Source structure: source_root / diff / scene / ID_instr.json
        scene_path = source_root / diff / scene
        
        if not scene_path.exists():
            # Try to handle case where Scene in report (FloorPlan18) matches folder
            # Sometimes case sensitivity might differ, but usually it matches
            print(f"Warning: Scene folder not found: {scene_path}")
            continue
            
        # Find json file matching instruction
        # File format: "06_wash_a_butterknife....json"
        # Instr: "wash_a_butterknife..."
        found = False
        for file_path in scene_path.glob("*.json"):
            # Check if filename contains instruction
            # e.g. "06_instr.json" -> split by first _
            stem = file_path.stem # remove .json
            parts = stem.split('_', 1)
            
            if len(parts) > 1 and parts[1] == instr:
                # Found match
                dst_dir = target_root / diff / scene
                dst_dir.mkdir(parents=True, exist_ok=True)
                
                shutil.copy2(file_path, dst_dir / file_path.name)
                copied_count += 1
                found = True
                break
        
        if not found:
            # Fallback: maybe instruction string in report is slightly different?
            # Or try contains match
            for file_path in scene_path.glob("*.json"):
                if instr in file_path.stem:
                    dst_dir = target_root / diff / scene
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, dst_dir / file_path.name)
                    copied_count += 1
                    found = True
                    break

    print(f"\nSuccessfully copied {copied_count} task JSON files to {target_root}")

if __name__ == "__main__":
    extract_failed_tasks()
