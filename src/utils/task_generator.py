import json
import os

from dotenv import load_dotenv
from openai import OpenAI


def get_openai_key():
    load_dotenv()
    return os.environ.get("OPENAI_API_KEY")


openai_api_key = get_openai_key()
client = OpenAI(api_key=openai_api_key)


def load_prompt(file_path):
    """Load the prompt examples and context from a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            prompt = file.read()
        return prompt
    except FileNotFoundError:
        print("Prompt file not found. Please check the file path.")
        return None


def generate_subtasks(messages):
    """Generate the subtasks decomposition from the user's task description."""

    # Using OpenAI API to get the response
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error getting response from OpenAI: {e}")
        return None


def save_to_file(data, file_name):
    """Save JSON data to a file."""
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        print(f"Output saved to {file_name}")
    except IOError as e:
        print(f"Error saving file: {e}")


def generate_task_by_llm():

    prompt_file_path = os.path.join("assets/prompts", f"e2e_generator.txt")

    examples_prompt = load_prompt(prompt_file_path)
    if examples_prompt is None:
        return

    user_input = input("Please enter your task description: ")
    full_prompt = [
        {"role": "system", "content": f"""{examples_prompt}"""},
        {"role": "assistant", "content": f"""\n\n### [Input] ###\n\n"""},
        {"role": "user", "content": f"""{user_input}"""},
    ]
    output = generate_subtasks(full_prompt)
    file_name = user_input.join("_")
    if output:
        try:
            # Convert the output text to JSON
            output_json = json.loads(output)
            # Save the JSON data to a file
            save_to_file(output_json, f"assets/tasks/task_{file_name}.json")
            return file_name
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")


if __name__ == "__main__":
    generate_task_by_llm()
