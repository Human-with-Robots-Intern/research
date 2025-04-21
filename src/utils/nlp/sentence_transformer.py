### utils/nlp/sentence_transformer.py
import numpy as np
from sentence_transformers import SentenceTransformer

from utils.common import create_module_logger

log = create_module_logger(__name__, module_log=True)


class SentenceSimilarityModel:
    _instance = None

    def __init__(self, model_name="all-MiniLM-L6-v2"):
        if SentenceSimilarityModel._instance is not None:
            raise RuntimeError("싱글톤 클래스이므로, get_instance()를 사용하세요.")

        log.warning("Loading SentenceTransformer model...")
        self.model = SentenceTransformer(model_name)
        SentenceSimilarityModel._instance = self

    @classmethod
    def get_instance(cls, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        if cls._instance is None:
            cls(model_name)
        return cls._instance

    def encode_sentence(self, sentence: str) -> np.ndarray:
        return self.model.encode(sentence, convert_to_numpy=True)

    def encode_sentences(self, sentences: list[str]) -> np.ndarray:
        return self.model.encode(sentences, convert_to_numpy=True)

    def compute_cosine_similarity(self, query_str: str, target_str: str) -> float:
        origin_vec = self.model.encode([query_str])[0]
        target_vec = self.model.encode([target_str])[0]
        return float(
            np.dot(origin_vec, target_vec)
            / (np.linalg.norm(origin_vec) * np.linalg.norm(target_vec))
        )

    def compute_batch_cosine_similarity(
        self, query_vec: np.ndarray, ref_vecs: np.ndarray
    ) -> np.ndarray:
        """
        Compute cosine similarity between a single query vector and a batch of reference vectors.

        Args:
            query_vec (np.ndarray): shape (embedding_dim,)
            ref_vecs (np.ndarray): shape (n_refs, embedding_dim)

        Returns:
            np.ndarray: shape (n_refs,), cosine similarities
        """
        query_norm = query_vec / np.linalg.norm(query_vec)
        ref_norms = ref_vecs / np.linalg.norm(ref_vecs, axis=1, keepdims=True)
        return np.dot(ref_norms, query_norm)
