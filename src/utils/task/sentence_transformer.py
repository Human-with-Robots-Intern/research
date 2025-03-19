# singleton_st.py
import numpy as np
from sentence_transformers import SentenceTransformer

from utils.util import create_module_logger

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

    def compute_cosine_similarity(
        self, query_str: str, target_strs: list[str]
    ) -> float:
        """
        Compute the cosine similarity between two embedding vectors.

        :param vec1: First embedding vector of shape (1, embedding_dim).
        :param vec2: Second embedding vector of shape (1, embedding_dim).
        :return: Cosine similarity score (float).
        """
        # INFO     Computing cosine similarity between 'Turn off stove after cooking' and ['Brew Coffee']
        log.info(f"Computing cosine similarity between '{query_str}' and {target_strs}")
        origin_vec = self.model.encode([query_str])
        target_vecs = self.model.encode(target_strs)
        return float(
            np.dot(origin_vec, target_vecs)
            / (np.linalg.norm(origin_vec) * np.linalg.norm(target_vecs))
        )
