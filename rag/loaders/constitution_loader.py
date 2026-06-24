"""
Loader for the Constitution of India PDF.
Uses LangChain's PyMuPDFLoader to extract text from the Constitution PDF.
"""

import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def load_constitution(constitution_dir: Path, limit: int = None) -> List[Document]:
    """
    Load the Constitution of India from PDF.
    
    Args:
        constitution_dir: Path to the directory containing the Constitution PDF.
        limit: Maximum number of pages to load (None = all).
        
    Returns:
        List of LangChain Documents, one per page, with metadata.
    """
    pdf_path = constitution_dir / "Constitution of India.pdf"
    
    if not pdf_path.exists():
        logger.warning(f"Constitution PDF not found at {pdf_path}")
        return []
    
    logger.info(f"Loading Constitution of India from {pdf_path}")
    
    loader = PyMuPDFLoader(str(pdf_path))
    pages = loader.load()
    
    if limit:
        pages = pages[:limit]
    
    # Enrich metadata on each page document
    documents = []
    for i, page in enumerate(pages):
        page.metadata.update({
            "source_type": "constitution",
            "title": "Constitution of India",
            "court": "N/A",
            "date": "1950-01-26",
            "jurisdiction": "India",
            "document_id": "constitution_of_india",
            "page_number": i + 1,
        })
        
        # Skip pages with very little text (blank pages, cover pages)
        if len(page.page_content.strip()) < 50:
            continue
        
        documents.append(page)
    
    logger.info(f"Loaded {len(documents)} pages from Constitution of India")
    return documents
