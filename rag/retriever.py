"""
Retriever pipeline using LangChain-native components:
- MultiQueryRetriever for diverse query generation
- ContextualCompressionRetriever with CrossEncoderReranker (BGE-Reranker-v2-m3)
"""

import logging

from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.language_models import BaseLanguageModel

from rag.prompts import MULTI_QUERY_PROMPT

logger = logging.getLogger(__name__)


def get_retriever(
    vectorstore,
    llm: BaseLanguageModel,
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3",
    retriever_top_k: int = 20,
    reranker_top_n: int = 6,
):
    """
    Build the two-stage retrieval pipeline:
    
    Stage 1: MultiQueryRetriever — generates 6 diverse legal queries,
             retrieves top-k candidates for each from ChromaDB.
    Stage 2: ContextualCompressionRetriever — reranks all candidates
             using BGE-Reranker-v2-m3 cross-encoder, returns top-n.
    
    Args:
        vectorstore: LangChain Chroma vector store.
        llm: LangChain LLM for multi-query generation.
        reranker_model_name: HuggingFace cross-encoder model for reranking.
        retriever_top_k: Number of initial candidates per query.
        reranker_top_n: Number of final results after reranking.
        
    Returns:
        ContextualCompressionRetriever (the final retriever to use).
    """
    # --- Stage 1: MultiQueryRetriever ---
    logger.info("Setting up MultiQueryRetriever")
    
    base_retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": retriever_top_k},
    )
    
    multi_query_retriever = MultiQueryRetriever.from_llm(
        retriever=base_retriever,
        llm=llm,
        prompt=MULTI_QUERY_PROMPT,
    )
    
    # --- Stage 2: CrossEncoderReranker ---
    logger.info(f"Loading reranker model: {reranker_model_name}")
    
    cross_encoder = HuggingFaceCrossEncoder(model_name=reranker_model_name)
    compressor = CrossEncoderReranker(
        model=cross_encoder,
        top_n=reranker_top_n,
    )
    
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=multi_query_retriever,
    )
    
    logger.info(
        f"Retriever pipeline ready: MultiQuery(k={retriever_top_k}) → "
        f"Reranker(top_n={reranker_top_n})"
    )
    
    return compression_retriever
