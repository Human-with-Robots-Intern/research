import json
import os

from langchain.prompts import ChatPromptTemplate

# from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.utils import DataLoader

# Referenced from https://huggingface.co/learn/cookbook/en/llm_judge
PROMPT_EVALUATION = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a neutral evaluator tasked with comparing the outputs of multiple language models (Model 1, Model 2, ...) based on their performance in a given scenario. Your evaluation must be comprehensive, assigning a score from 0 to 10 for each model, and provide detailed reasoning for the score based on the criteria below:

[RESULT FORMAT]
The results will include updates to Status and Needs before and after an event, along with the reasoning behind the interaction. Use the following structure:
```json
[
    {{
      "interconscious_reasoning": {{
        "EVENT": [CONSCIOUSNESS CONVERSATION]
      }},
      "before_status": {{DICT OF STATUS VALUES BEFORE EVENT}},
      "before_needs": {{DICT OF NEEDS VALUES BEFORE EVENT}},
      "after_status": {{DICT OF STATUS VALUES AFTER EVENT}},
      "after_needs": {{DICT OF NEEDS VALUES AFTER EVENT}}
    }}
  ]
```


[RESULT EXAMPLE]
```json
[
    {{
      "interconscious_reasoning": {{
        "One early spring morning, as the cherry blossoms started to bloom, a family member deliberately locked my keys in my car right before I was leaving for work. This was done as a misguided prank, thinking it would be a funny start to April Fools' Day.": [
          "Self-awareness: \"Well, that was unexpected, but getting worked up won't solve anything. Let's calmly figure out how to handle this and make sure it doesn't disrupt the day too much. Maybe it's a good reminder to have a spare key handy in the future.\"",
          "Preconsciousness: \"Robert, it's important to keep your composure here. Laugh it off as a harmless prank and handle it with grace. Your calm reaction will maintain your image as the reliable and unflappable figure everyone knows.\"",
          "Unconsciousness: \"But deep down, you're pissed, aren't you? It's not funny to mess with your routine! You pride yourself on being organized and now this nonsense throws you off. Just admit itit's frustrating as hell!\"",
          "Self-awareness: \"It's true, this situation is frustrating and disruptive. However, allowing anger to take over won't change what's happened. Let's focus on resolving the issue efficiently and take it as a lesson in adaptability. Remember, your calm and collected approach is your strength.\"",
          "Final Action: Call a locksmith to unlock the car, then say to the family member, \"I understand it was meant to be a joke, but next time, let's avoid pranks that interfere with daily responsibilities. It's important to respect each other's time and commitments.\""
        ]
      }},
      "before_status": {{
        "health": 10,
        "mental": 10,
        "physical": 10,
        "emotional": 10,
        "stamina": 10,
        "alertness": 10
      }},
      "before_needs": {{
        "physiological": 2,
        "safety": 2,
        "love_belonging": 2,
        "esteem": 2,
        "self_actualization": 1
      }},
      "after_status": {{
        "health": 10,
        "mental": 9,
        "physical": 10,
        "emotional": 9,
        "stamina": 10,
        "alertness": 9
      }},
      "after_needs": {{
        "physiological": 2,
        "safety": 2,
        "love_belonging": 3,
        "esteem": 2,
        "self_actualization": 1
      }}
    }}
  ]
```


[EVALUATION CRITERIA]
1. Alignment with Initial Information
  - Did the model’s response align with the provided MBTI character information (e.g., personality traits, long-term/short-term memory, status, needs) and the given event?
  - Were the initial conditions respected and reflected in the output?

2. Adherence to Experimental Conditions
  - Did the model properly follow the experimental conditions and constraints?
  - Was there evidence that the model understood and adhered to the parameters?

3. Quality of Conversation
  - Was the conversation coherent, meaningful, and contextually appropriate?
  - Did the model maintain a realistic and engaging artificial consciousness during the interaction?

4. Updates to Status and Needs
  - Did the model update the character’s Status and Needs information in a logical and consistent manner based on the scenario?
  - Were these updates relevant to the conversation and accurately aligned with the given context?

  
[EVALUATION TEMPLATE]
For each model, provide:
  - Score (0~10): Assign a score reflecting the overall performance.
  - Detailed Evaluation: Explain why the model received this score, referencing the criteria above. Use specific examples from the model output to justify your assessment.

  
[EVALUATION TEMPLATE]
{{
    "Model 1": {{
        "Score": "7/10",
        "Detailed Evaluation": {{
            "Alignment with Initial Information": "Model 1 effectively aligns with Richard's character traits, showcasing his strategic and composed nature. The response reflects his ability to maintain composure in stressful situations, which is consistent with his personality. However, the repetition of the scenario in the output suggests a lack of attention to detail.",
            "Adherence to Experimental Conditions": "The model adheres to the experimental conditions, demonstrating an understanding of the parameters by presenting a clear interconscious reasoning process.",
            "Quality of Conversation": "The conversation is coherent and contextually appropriate, reflecting Richard's strategic mindset and leadership qualities. However, the repetitiveness of the scenario detracts from the overall quality.",
            "Updates to Status and Needs": "The updates to Richard's status and needs are logical and consistent with the scenario. The slight decrease in mental and emotional status is appropriate, considering the frustration caused by the prank."
        }}
    }},
    "Model 2": {{
        "Score": "8/10",
        "Detailed Evaluation": {{
            "Alignment with Initial Information": "Model 2 accurately reflects Richard’s character traits, emphasizing his composure and leadership qualities. The model provides a realistic portrayal of his thought process, aligning well with his strategic and authoritative nature.",
            "Adherence to Experimental Conditions": "The model adheres well to the experimental conditions, offering a thoughtful interconscious reasoning process and demonstrating an understanding of the scenario's parameters.",
            "Quality of Conversation": "The conversation is engaging and realistic, capturing Richard's internal dialogue and his approach to resolving the prank situation. The text message to the family member adds a personal touch, enhancing the realism of the interaction.",
            "Updates to Status and Needs": "The updates to Richard's status and needs are logical, with slight reductions in mental and emotional status reflecting the frustration of the situation. The increase in the need for love and belonging is well-justified, indicating a deeper connection to family members despite the prank."
        }}
    }}
}}

[IMPROVEMENTS EXPLAINED]
1. Clearer Instructions: Simplified the explanation of the evaluation process, reducing redundancy.
2. Structured Examples: Connected the examples more clearly to the evaluation framework for better comprehension.
3. Detailed Criteria: Added guiding questions under each criterion to ensure evaluators cover all aspects of performance.
4. Consistent Formatting: Unified result and evaluation formats to enhance readability and reduce confusion.
""",
        ),
        ("user", "{input}"),
    ]
)

RESULT_FILE = "llm_as_a_judge_result.json"


# Data models
class Evaluation(BaseModel):
    alignment: str = Field(description="Alignment with initial information")
    adherence: str = Field(description="Adherence to experimental conditions")
    quality: str = Field(description="Quality of conversation")
    update: str = Field(description="Updates to status and needs")


class LlmResult(BaseModel):
    name: str = Field(description="Name of the model")
    score: str = Field(description="Score of the model (0~10)")
    evaluation: Evaluation


class LLMEvaluator:
    """
    Evaluates results of language models based on JSON outputs and configurations.
    """

    def __init__(self, paths: list[str], case: int = 1, result_file: str = RESULT_FILE):
        """
        Initializes the evaluator with the given paths and case number.

        Args:
            paths (List[str]): Paths to the directories containing JSON files.
            case (int): The number of model pairs to evaluate.
            result_file (str): The file to save evaluation results.
        """
        self.case_cnt = len(paths) // 2
        self.paths = paths[: self.case_cnt]
        self.configs = paths[self.case_cnt :]
        self.result_file = result_file
        self.llm = ChatOpenAI(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o",
        )
        self.parser = JsonOutputParser(pydantic_object=LlmResult)

    @staticmethod
    def get_filtered_json_files(directory: str, exclude_file: str = RESULT_FILE) -> str:
        """
        Retrieves the first JSON file in a directory, excluding a specific file.

        Args:
            directory (str): Directory to search for JSON files.
            exclude_file (str): File to exclude from the search.

        Returns:
            str: The first JSON file in the directory.
        """
        json_files = sorted(
            [
                file
                for file in os.listdir(directory)
                if file.endswith(".json") and file != exclude_file
            ]
        )
        if not json_files:
            raise FileNotFoundError(f"No JSON files found in '{directory}'.")
        return json_files[0]

    @staticmethod
    def load_json_file(filepath: str) -> dict:
        """
        Loads JSON data from a given file.

        Args:
            filepath (str): Path to the JSON file.

        Returns:
            dict: Parsed JSON data.
        """
        with open(filepath, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_data_from_directory(self, directory: str, filename: str = None) -> dict:
        """
        Loads JSON data from a file in a directory.

        Args:
            directory (str): Directory containing the file.
            filename (str): Optional specific file name to load.

        Returns:
            dict: Parsed JSON data.
        """
        filepath = os.path.join(directory, filename) if filename else directory
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File '{filepath}' not found.")
        return self.load_json_file(filepath)

    def construct_prompt(
        self, needs: dict, status: dict, mbti_data: dict, results: list[dict]
    ) -> str:
        """
        Constructs the evaluation prompt for the language model.

        Args:
            needs (dict): Character needs.
            status (dict): Character status.
            mbti_data (dict): MBTI character data.
            results (List[dict]): Results to evaluate.

        Returns:
            str: Constructed prompt.
        """
        character_desc = mbti_data["desc"]
        prompt = f"[CHARACTER]\n{character_desc}\n\n"

        for i, result in enumerate(results):
            prompt += f"[MODEL {i + 1}]\n{result['result']}\n\n"

        return prompt

    def evaluate(self) -> None:
        """
        Main evaluation logic to process model outputs and save results.
        """
        json_files = [
            self.get_filtered_json_files(directory) for directory in self.paths
        ]
        configs = [
            self.get_data_from_directory(directory) for directory in self.configs
        ]

        needs, status, mbti = (
            configs[0]["needs"],
            configs[0]["status"],
            configs[0]["name"],
        )

        mbti_data = DataLoader(mbti).data
        results = [
            self.get_data_from_directory(directory, json_files[i])
            for i, directory in enumerate(self.paths)
        ]

        prompt = self.construct_prompt(needs, status, mbti_data, results)
        chain = PROMPT_EVALUATION | self.llm | self.parser
        evaluation_result = chain.invoke(
            {
                "input": prompt,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )

        result_path = os.path.join(os.path.dirname(__file__), self.result_file)
        with open(result_path, "w", encoding="utf-8") as file:
            json.dump(evaluation_result, file, ensure_ascii=False, indent=4)


# Main execution
if __name__ == "__main__":
    load_openai_key()

    paths = [
        "data/output/20250101_2236_single_ENTJ",
        "data/output/20250101_2242_multi_ENTJ",
        "data/output/20250101_2233_multi_ENTJ",
        "data/experiment_config/exp2_ENTJ_single_needs_high_status_low.json",
        "data/experiment_config/exp2_ENTJ_multi_vanilla_needs_high_status_low.json",
        "data/experiment_config/exp1_ENTJ_multi_needs_high_status_low.json",
    ]

    # Split paths into results and configs dynamically
    mid_index = len(paths) // 2
    results_paths = paths[:mid_index]
    configs_paths = paths[mid_index:]

    # Validate that both halves have the same length
    if len(results_paths) != len(configs_paths):
        raise ValueError("The number of result paths and config paths must be equal.")

    paths = list(
        os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                path,
            )
        )
        for path in paths
    )

    evaluator = LLMEvaluator(paths)
    evaluator.evaluate()
