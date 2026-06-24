"""
Main RAG chain orchestration.
Initializes all components and provides the ask() interface.
Uses LangGraph's checkpointer for per-session chat memory.
"""

import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_ollama import ChatOllama

from app.config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    EMBEDDING_MODEL_NAME,
    GOOGLE_API_KEY,
    LLM_MODEL_NAME,
    RERANKER_MODEL_NAME,
    RERANKER_TOP_N,
    RETRIEVER_TOP_K,
)
from rag.agent import build_agent
from rag.embeddings import get_embedding_model
from rag.retriever import get_retriever
from rag.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)


class LegalRAGChain:
    """
    Main orchestrator for the Legal RAG Chatbot.
    
    Initializes all components (embeddings, vectorstore, retriever, agent)
    and provides the ask() method for processing user queries.
    """
    
    def __init__(self):
        """Initialize all RAG pipeline components."""
        logger.info("=" * 60)
        logger.info("Initializing Legal RAG Chain")
        logger.info("=" * 60)
        
        # Step 1: Initialize LLM
        logger.info(f"Initializing LLM: {LLM_MODEL_NAME}")
        self.llm = ChatOllama(
            model=LLM_MODEL_NAME,
            temperature=0.1,
        )
        
        # Step 2: Initialize embedding model
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        self.embedding_model = get_embedding_model(EMBEDDING_MODEL_NAME)
        
        # Step 3: Initialize vector store
        logger.info("Connecting to ChromaDB vector store")
        self.vectorstore = get_vectorstore(
            embedding_model=self.embedding_model,
            persist_directory=CHROMA_DB_DIR,
            collection_name=CHROMA_COLLECTION_NAME,
        )
        
        # Step 4: Build retriever pipeline
        logger.info("Building retriever pipeline (MultiQuery + Reranker)")
        self.retriever = get_retriever(
            vectorstore=self.vectorstore,
            llm=self.llm,
            reranker_model_name=RERANKER_MODEL_NAME,
            retriever_top_k=RETRIEVER_TOP_K,
            reranker_top_n=RERANKER_TOP_N,
        )
        
        # Step 5: Build agent
        logger.info("Building ReAct agent (LangGraph)")
        self.agent = build_agent(
            llm=self.llm,
            retriever=self.retriever,
        )
        
        logger.info("=" * 60)
        logger.info("Legal RAG Chain initialized successfully")
        logger.info("=" * 60)
    
    def ask(self, question: str, session_id: str = "default") -> str:
        """
        Process a user question through the RAG pipeline.
        
        Args:
            question: The user's legal question.
            session_id: Unique session ID for chat history.
            
        Returns:
            The agent's response string.
        """
        logger.info(f"Processing question (session={session_id}): {question[:100]}...")
        
        try:
            config = {"configurable": {"thread_id": session_id}}
            response = self.agent.invoke(
                {"messages": [("user", question)]},
                config=config,
            )
            
            answer = response["messages"][-1].content
            logger.info(f"Response generated (length={len(answer)})")
            return answer
            
        except Exception as e:
            logger.error(f"Error processing question: {e}", exc_info=True)
            return (
                "I encountered an error while processing your question. "
                "Please try rephrasing or ask a different question.\n\n"
                f"Error details: {str(e)}"
            )
    
    def new_chat(self, session_id: str) -> None:
        """Clear the chat history for a session by clearing its memory saver state."""
        # For LangGraph memory saver, it's tied to thread_id. 
        # A simple way to clear chat for the client is just to generate a new session_id on the frontend.
        # But if the backend needs to forcefully clear a thread, we can do it via the checkpointer.
        config = {"configurable": {"thread_id": session_id}}
        
        # MemorySaver doesn't have an easy "clear" but we can put an empty state
        # In a real app with persistent db, we'd delete the thread. For MemorySaver, it's fine.
        logger.info(f"Chat session reset requested for: {session_id}. Handled implicitly by new UI session ID.")

