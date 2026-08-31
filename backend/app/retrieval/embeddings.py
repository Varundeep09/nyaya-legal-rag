"""
Dense embeddings module for Nyaya Legal Assistant using BAAI/bge-base-en-v1.5.
Supports asymmetric passage and query embeddings with L2 normalization for pgvector storage.
"""

from typing import List, Tuple, Optional
from sentence_transformers import SentenceTransformer
from app.core.logging import logger

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EXPECTED_DIMENSION = 768

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """
    Lazy loads and returns the BAAI/bge-base-en-v1.5 SentenceTransformer model singleton.
    Validates model max_seq_length and embedding dimension.
    """
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        real_max_seq = _model.max_seq_length
        real_dim = _model.get_sentence_embedding_dimension()

        print(f"[Embedding Model] Loaded {MODEL_NAME}")
        print(f"[Embedding Model] Real model.max_seq_length: {real_max_seq}")
        print(f"[Embedding Model] Real embedding dimension: {real_dim}")

        if real_dim != EXPECTED_DIMENSION:
            raise ValueError(
                f"Embedding dimension mismatch! Model returned {real_dim}, but database Vector({EXPECTED_DIMENSION}) expected."
            )
        logger.info(f"Model {MODEL_NAME} loaded: max_seq_length={real_max_seq}, dim={real_dim}")
    return _model


def check_token_length(text: str) -> Tuple[bool, int]:
    """
    Tokenizes input text with real model tokenizer and checks if it exceeds max_seq_length.
    Returns (is_exceeded, token_count).
    """
    model = get_embedding_model()
    # Tokenize with passage prefix to measure exact input tokens fed to model
    prefixed_text = f"passage: {text}"
    tokens = model.tokenizer(prefixed_text)["input_ids"]
    token_count = len(tokens)
    is_exceeded = token_count > model.max_seq_length
    return is_exceeded, token_count


def embed_passages(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """
    Embeds a list of document/statute passages with asymmetric 'passage: ' prefix and L2 normalization.
    Returns plain Python list of float vectors for pgvector storage.
    """
    if not texts:
        return []

    model = get_embedding_model()
    prefixed_texts = [f"passage: {t}" for t in texts]

    embeddings = model.encode(
        prefixed_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    # Convert numpy ndarray to list of python floats
    return embeddings.tolist()


def embed_query(text: str) -> List[float]:
    """
    Embeds a user query with asymmetric 'query: ' prefix and L2 normalization.
    Returns plain Python list of floats.
    """
    model = get_embedding_model()
    prefixed_query = f"query: {text}"

    embedding = model.encode(
        prefixed_query,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    return embedding.tolist()
