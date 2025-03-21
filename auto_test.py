# auto_test.py
import subprocess

from utils.constants import TOP_K


def run_automated_tests(num_runs_per_instruction=2):
    """
    'main.py'를 외부 프로세스로 실행하면서
    새로운 인스트럭션(0번 선택)을 자동으로 입력해주는 예제.
    """
    instructions = [
        "prepare vegetables for lunch and cook egg fry",
        "make coffee and wash plates and store tomato in fridge",
        "cook egg fry and wash plates and put creditcard on shelf",
        "cook egg fry and heat bread using microwave and make coffee and heat potato using microwave and wash vegetables and wash cutlery and wash dishes",
        "wash egg and cook egg fry and heat bread using microwave and make coffee and put creditcard on shelf and throw away paper towel and wash cutlery and wash dishes and wash vegetables and organize the vegetables",
    ]
    for i in range(len(instructions)):
        for j in range(num_runs_per_instruction):

            instruction_text = f"{instructions[i]}"

            input_str = f"0\n{instruction_text}\n"

            print(f"\n[테스트 실행] {i+1}번째 인스트럭션 중 {j+1}회차")
            print(f" - 자동 입력: \n{input_str}")

            # main.py를 실행하면서 input_str을 표준 입력으로 전달
            subprocess.run(
                [
                    "python",
                    "src/dag_bayesian.py",
                ],  # 필요 시 경로나 가상환경 등을 맞게 수정
                input=input_str,
                text=True,
                check=True,
            )


if __name__ == "__main__":
    print(f"TOP_{TOP_K}_RAG")
    run_automated_tests(num_runs_per_instruction=5)
