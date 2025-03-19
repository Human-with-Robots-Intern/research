import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from utils.task.sentence_transformer import SentenceSimilarityModel


class FewShotRetriever:
    def __init__(self) -> None:
        """
        Initialize the FewShotRetriever class.

        :param model_name: Name of the sentence-transformers model to use.
        """
        self.model = SentenceSimilarityModel().get_instance

    def semantic_search(
        self,
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
            score = self.model.compute_cosine_similarity(query_vec, ref_vec)
            sim_scores.append((idx, score))
        sim_scores.sort(key=lambda x: x[1], reverse=True)

        top_k_idx = [idx for idx, _ in sim_scores[:k]]
        return top_k_idx

    def generate_few_shot_prompts(
        self,
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

        # Load the dictionary of reference tasks
        with open(nl_task_db_path, "r") as f:
            refer_dict = json.load(f)

        # Prepare lists for embedding
        refer_nls = list(refer_dict.keys())

        # Get top-k similar indices
        top_k_idx = self.semantic_search(input_nl, refer_nls, k=top_k)

        # Retrieve the corresponding references
        top_k_dict = {refer_nls[idx]: refer_dict[refer_nls[idx]] for idx in top_k_idx}

        few_shot_prompt = ""
        # Print few-shot prompts
        for idx, (task_nl, task_file_name) in enumerate(top_k_dict.items(), start=1):
            with open(tasks_dir / task_file_name, "r") as f:
                task_data = json.load(f)
                few_shot_output = json.dumps(task_data, indent=4)

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
