# run_all.py
import subprocess
import time

def run_with_retries(script, max_retries=3):
    for attempt in range(1, max_retries + 1):
        print(f"Running {script} (Attempt {attempt})...")
        result = subprocess.run(["python", script])
        if result.returncode == 0:
            return True
        elif attempt < max_retries:
            print(f"Retrying {script} after failure (Attempt {attempt})...")
            time.sleep(2)  # 짧은 대기 시간 후 재시도
    return False  # 모든 시도 실패

scripts = [
    "src/baselines/progprompt/prog-ai2thor.py",
    "src/baselines/cap/cap-ai2thor.py",
    "src/dag_bayesian.py",
    "src/baselines/cpm.py",
    "src/baselines/edf/dag_edf.py"
]

# 재시도 대상 스크립트들
retry_scripts = {
    "src/baselines/progprompt/prog-ai2thor.py",
    "src/baselines/cap/cap-ai2thor.py"
}

for script in scripts:
    if script in retry_scripts:
        success = run_with_retries(script, max_retries=5)
    else:
        print(f"Running {script}...")
        result = subprocess.run(["python", script])
        success = result.returncode == 0

    if not success:
        print(f"Error occurred while running {script}. Aborting.")
        break  # 에러 발생 시 전체 실행 중단
