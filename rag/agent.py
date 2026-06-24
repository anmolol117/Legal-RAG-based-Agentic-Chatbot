"""
LangChain ReAct Agent with legal search and web search tools.
Uses create_react_agent + AgentExecutor with RunnableWithMessageHistory.
"""

import logging
from typing import List

from langgraph.prebuilt import create_react_agent
import os
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import CHROMA_DB_DIR
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.language_models import BaseLanguageModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools import Tool

from rag.prompts import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _format_docs(docs) -> str:
    """Format retrieved documents into a readable context string."""
    if not docs:
        return "No relevant documents found."
    
    formatted = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        source_type = meta.get("source_type", "unknown")
        title = meta.get("title", "Unknown")
        section_type = meta.get("section_type", "")
        date = meta.get("date", "")
        court = meta.get("court", "")
        
        header = f"[Source {i}] {title}"
        if court:
            header += f" | {court}"
        if date:
            header += f" | {date}"
        if section_type:
            header += f" | Section: {section_type}"
        header += f" | Type: {source_type}"
        
        formatted.append(f"{header}\n{doc.page_content}")
    
    return "\n\n---\n\n".join(formatted)


def _create_legal_search_tool(retriever: BaseRetriever) -> Tool:
    """Create a LangChain Tool wrapping the legal retriever pipeline."""
    
    def search_legal_db(query: str) -> str:
        """Search the legal knowledge base for relevant documents."""
        try:
            docs = retriever.invoke(query)
            return _format_docs(docs)
        except Exception as e:
            logger.error(f"Legal search failed: {e}")
            return f"Legal search encountered an error: {str(e)}"
    
    return Tool(
        name="legal_search",
        description=(
            "Search the legal knowledge base containing Indian statutes (India Code), "
            "the Constitution of India, Supreme Court judgments, RBI circulars, and "
            "SEBI regulations. Use this tool to find relevant legal provisions, "
            "case law, regulatory guidelines, and legal principles. "
            "Input should be a detailed legal search query."
        ),
        func=search_legal_db,
    )


def _create_web_search_tool() -> Tool:
    """Create a custom DuckDuckGo web search tool."""
    
    def web_search(query: str) -> str:
        """Search the web using DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No results found on the web."
            
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(f"[{i}] {r.get('title', '')}\n{r.get('body', '')}\nURL: {r.get('href', '')}")
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return f"Web search encountered an error: {str(e)}"

    return Tool(
        name="web_search",
        description=(
            "Search the web for recent legal updates, amendments, new regulations, "
            "court decisions, or legal news that may not be in the knowledge base. "
            "Use this tool when the user asks about very recent changes to laws, "
            "ongoing cases, or current legal developments in India."
        ),
        func=web_search,
    )


def build_agent(
    llm: BaseLanguageModel,
    retriever: BaseRetriever,
):
    """
    Build the LangGraph ReAct agent with legal_search and web_search tools.
    
    Args:
        llm: LangChain LLM (Gemini 2.5 Flash).
        retriever: The ContextualCompressionRetriever (MultiQuery + Reranker).
        
    Returns:
        Compiled LangGraph agent.
    """
    logger.info("Building ReAct agent with legal_search and web_search tools")
    
    # Create tools
    legal_search_tool = _create_legal_search_tool(retriever)
    web_search_tool = _create_web_search_tool()
    tools = [legal_search_tool, web_search_tool]
    
    # Create persistent memory saver using SQLite
    db_path = os.path.join(CHROMA_DB_DIR, "checkpoints.sqlite")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)
    memory.setup()
    
    # Create LangGraph ReAct agent
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=AGENT_SYSTEM_PROMPT,
        checkpointer=memory,
    )
    
    logger.info("LangGraph ReAct agent built successfully")
    return agent
