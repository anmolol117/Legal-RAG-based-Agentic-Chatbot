"""
ChromaDB vector store setup using langchain-chroma.
"""

import logging
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


def get_vectorstore(
    embedding_model: Embeddings,
    persist_directory: str = "./chroma_db",
    collection_name: str = "legal_documents",
) -> Chroma:
    """
    Initialize and return a ChromaDB vector store via LangChain.
    
    Args:
        embedding_model: LangChain Embeddings instance.
        persist_directory: Directory for ChromaDB persistence.
        collection_name: Name of the ChromaDB collection.
        
    Returns:
        LangChain Chroma instance.
    """
    logger.info(
        f"Initializing ChromaDB at '{persist_directory}', "
        f"collection='{collection_name}'"
    )
    
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embedding_model,
        persist_directory=persist_directory,
    )
    
    logger.info("ChromaDB vector store initialized")
    return vectorstore


def add_documents_to_vectorstore(
    vectorstore: Chroma,
    documents: List[Document],
    batch_size: int = 100,
) -> None:
    """
    Add documents to the vector store in batches.
    
    Args:
        vectorstore: LangChain Chroma instance.
        documents: List of LangChain Documents to add.
        batch_size: Number of documents per batch.
    """
    total = len(documents)
    logger.info(f"Adding {total} documents to ChromaDB in batches of {batch_size}")
    
    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        vectorstore.add_documents(batch)
        logger.info(f"  Added batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size}")
    
    logger.info(f"Successfully added {total} documents to ChromaDB")


def reset_vectorstore(
    embedding_model: Embeddings,
    persist_directory: str = "./chroma_db",
    collection_name: str = "legal_documents",
) -> Chroma:
    """
    Reset (delete and recreate) the vector store collection.
    
    Args:
        embedding_model: LangChain Embeddings instance.
        persist_directory: Directory for ChromaDB persistence.
        collection_name: Name of the ChromaDB collection.
        
    Returns:
        Fresh LangChain Chroma instance.
    """
    import chromadb
    
    logger.warning(f"Resetting ChromaDB collection '{collection_name}'")
    
    client = chromadb.PersistentClient(path=persist_directory)
    
    # Delete existing collection if it exists
    try:
        client.delete_collection(collection_name)
        logger.info(f"Deleted existing collection '{collection_name}'")
    except Exception:
        logger.info(f"Collection '{collection_name}' does not exist, nothing to delete")
    
    # Return a fresh vector store
    return get_vectorstore(embedding_model, persist_directory, collection_name)
