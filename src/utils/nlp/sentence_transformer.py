# singleton_st.py
import numpy as np
from sentence_transformers import SentenceTransformer

from utils.common.util import create_module_logger

log = create_module_logger(__name__, module_log=True)


class SentenceSimilarityModel:
    _instance = None

    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        if SentenceSimilarityModel._instance is not None:
            raise Exception("싱글톤 클래스이므로, get_instance()를 사용하세요.")

        print("Loading SentenceTransformer model...")
        self.model = SentenceTransformer(model_name)
        SentenceSimilarityModel._instance = self

    @classmethod
    def get_instance(cls, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        if cls._instance is None:
            cls(model_name)
        return cls._instance

    def compute_cosine_similarity(self, query_str: str, target_str: str) -> float:
        """
        Compute the cosine similarity between two embedding vectors.

        :param vec1: First embedding vector of shape (1, embedding_dim).
        :param vec2: Second embedding vector of shape (1, embedding_dim).
        :return: Cosine similarity score (float).
        """

        origin_vec = self.model.encode([query_str])
        target_vec = self.model.encode(target_str)
        return float(
            np.dot(origin_vec, target_vec)
            / (np.linalg.norm(origin_vec) * np.linalg.norm(target_vec))
        )
