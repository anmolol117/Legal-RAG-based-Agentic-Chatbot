"""
Embedding model setup using LangChain's HuggingFace integration.
Uses BAAI/bge-m3 via HuggingFaceBgeEmbeddings.
"""

import logging

from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)


def get_embedding_model(model_name: str = "BAAI/bge-m3") -> HuggingFaceEmbeddings:
    """
    Initialize and return the BGE-M3 embedding model via LangChain wrapper.
    
    Args:
        model_name: HuggingFace model name for embeddings.
        
    Returns:
        LangChain HuggingFaceEmbeddings instance.
    """
    logger.info(f"Loading embedding model: {model_name}")
    
    embedding_model = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    
    logger.info(f"Embedding model loaded: {model_name}")
    return embedding_model
