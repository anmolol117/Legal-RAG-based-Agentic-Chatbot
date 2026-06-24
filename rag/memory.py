"""
Chat memory management using LangChain-native components.
Uses ChatMessageHistory with a session-based store.
"""

import logging
from typing import Dict

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory

logger = logging.getLogger(__name__)

# In-memory session store: maps session_id → ChatMessageHistory
_session_store: Dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """
    Get or create a ChatMessageHistory for the given session.
    
    This function is passed to RunnableWithMessageHistory to provide
    per-session chat history management.
    
    Args:
        session_id: Unique session identifier.
        
    Returns:
        ChatMessageHistory instance for this session.
    """
    if session_id not in _session_store:
        logger.info(f"Creating new chat session: {session_id}")
        _session_store[session_id] = ChatMessageHistory()
    return _session_store[session_id]


def clear_session(session_id: str) -> None:
    """
    Clear the chat history for a given session.
    
    Args:
        session_id: Session to clear.
    """
    if session_id in _session_store:
        _session_store[session_id].clear()
        logger.info(f"Cleared chat session: {session_id}")


def delete_session(session_id: str) -> None:
    """
    Completely remove a session from the store.
    
    Args:
        session_id: Session to delete.
    """
    if session_id in _session_store:
        del _session_store[session_id]
        logger.info(f"Deleted chat session: {session_id}")


def list_sessions() -> list:
    """Return a list of all active session IDs."""
    return list(_session_store.keys())
