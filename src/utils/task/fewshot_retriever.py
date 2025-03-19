import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


def load_json(json_file_path: Path) -> Dict:
    """
    Load a JSON file from the specified path and return its contents.
    """
    with open(json_file_path, "r") as f:
        return json.load(f)


def embed_data(data: List[str], model: SentenceTransformer) -> np.ndarray:
    """
    Embed a list of strings using the given SentenceTransformer model.

    :param data: List of input strings to embed.
    :param model: A SentenceTransformer model used for encoding.
    :return: NumPy array of embeddings, shape (len(data), embedding_dim).
    """
    return model.encode(data)


def compute_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Compute the cosine similarity between two embedding vectors.

    :param vec1: First embedding vector of shape (1, embedding_dim).
    :param vec2: Second embedding vector of shape (1, embedding_dim).
    :return: Cosine similarity score (float).
    """
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))


def semantic_search(
    query_vec: np.ndarray,
    references: np.ndarray,
    k: int = 5,
) -> List[int]:
    """
    Given a query embedding and a list of reference embeddings,
    compute cosine similarities and return the indices of the top-k matches.

    :param query_vec: Query embedding, shape (1, embedding_dim).
    :param references: Reference embeddings, shape (num_refs, embedding_dim).
    :param k: Number of top matches to return.
    :return: List of indices corresponding to the top-k highest similarity scores.
    """
    sim_scores = []
    for idx, ref_vec in enumerate(references):
        score = compute_cosine_similarity(query_vec, ref_vec)
        sim_scores.append((idx, score))
    sim_scores.sort(key=lambda x: x[1], reverse=True)

    top_k_idx = [idx for idx, _ in sim_scores[:k]]
    return top_k_idx


def generate_few_shot_prompts(
    input_nl: str,
    top_k: int,
    nl_task_db_path: Path = Path("assets/nl_task_db.json"),
    tasks_dir: Path = Path("assets/tasks"),
) -> None:
    """
    Generate and print few-shot prompts based on semantic similarity.

    1. Load the reference dictionary from a JSON database.
    2. Embed both the input natural language query and all reference keys.
    3. Find the top-k most similar references using cosine similarity.
    4. For each reference in the top-k, load the corresponding JSON file
       and print out a formatted prompt.

    :param input_nl: The input natural language string (query).
    :param nl_task_db_path: Path to the JSON file containing reference data.
    :param tasks_dir: Directory where the individual task JSON files are stored.
    :param top_k: Number of top matches to retrieve from the reference data.
    :param model_name: Name of the sentence-transformers model to use.
    """

    # Initialize the sentence-transformers model
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # Load the dictionary of reference tasks
    refer_dict = load_json(nl_task_db_path)

    # Prepare lists for embedding
    refer_nls = list(refer_dict.keys())

    # Embed the input and references
    input_nl_vec = embed_data([input_nl], model)
    refer_vec = embed_data(refer_nls, model)

    # Get top-k similar indices
    top_k_idx = semantic_search(input_nl_vec, refer_vec, k=top_k)

    # Retrieve the corresponding references
    top_k_dict = {refer_nls[idx]: refer_dict[refer_nls[idx]] for idx in top_k_idx}

    few_shot_prompt = ""
    # Print few-shot prompts
    for idx, (task_nl, task_file_name) in enumerate(top_k_dict.items(), start=1):
        few_shot_output = load_json(tasks_dir / task_file_name)

        few_shot_prompt += f"""
    ### **Example {idx}**
    
    **Input**
    ```
    {task_nl}
    ```
    
    **Output**
    ```json
    {few_shot_output}
    ```
    
    ---
    """
        return few_shot_prompt
