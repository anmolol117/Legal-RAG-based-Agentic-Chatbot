"""
Loader for India Code Central Acts.
Walks the central-acts directory, reads metadata.json for each act,
and loads PDFs using LangChain's PyMuPDFLoader.
"""

import json
import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def load_indiacode(indiacode_dir: Path, limit: int = None) -> List[Document]:
    """
    Load India Code Central Acts from the scraped data directory.
    
    Args:
        indiacode_dir: Path to the central-acts directory.
        limit: Maximum number of acts to process (None = all).
        
    Returns:
        List of LangChain Documents with act metadata.
    """
    if not indiacode_dir.exists():
        logger.warning(f"India Code directory not found at {indiacode_dir}")
        return []
    
    documents = []
    act_dirs = sorted([d for d in indiacode_dir.iterdir() if d.is_dir()])
    
    if limit:
        act_dirs = act_dirs[:limit]
    
    logger.info(f"Loading India Code acts from {indiacode_dir} ({len(act_dirs)} acts)")
    
    for act_dir in act_dirs:
        metadata_file = act_dir / "metadata.json"
        if not metadata_file.exists():
            logger.debug(f"No metadata.json in {act_dir}, skipping")
            continue
        
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                act_metadata = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read metadata from {metadata_file}: {e}")
            continue
        
        act_title = act_metadata.get("title", "Unknown Act")
        act_year = act_metadata.get("year", "Unknown")
        act_number = act_metadata.get("act_number", "Unknown")
        ministry = act_metadata.get("ministry_or_department", "Unknown")
        keywords = act_metadata.get("keywords", "")
        act_handle = act_metadata.get("act_handle", act_dir.name)
        
        # Process each document entry in the metadata
        doc_entries = act_metadata.get("documents", [])
        
        for doc_entry in doc_entries:
            relative_path = doc_entry.get("relative_path", "")
            if not relative_path:
                continue
            
            pdf_path = act_dir / relative_path
            if not pdf_path.exists() or not str(pdf_path).lower().endswith(".pdf"):
                continue
            
            section_type = doc_entry.get("section", "Act").lower()
            doc_label = doc_entry.get("document_label", "")
            doc_language = doc_entry.get("language", "english")
            
            # Skip non-English documents
            if doc_language != "english":
                continue
            
            try:
                loader = PyMuPDFLoader(str(pdf_path))
                pages = loader.load()
            except Exception as e:
                logger.warning(f"Failed to load PDF {pdf_path}: {e}")
                continue
            
            for i, page in enumerate(pages):
                if len(page.page_content.strip()) < 50:
                    continue
                
                page.metadata.update({
                    "source_type": "central_act",
                    "title": act_title,
                    "year": act_year,
                    "act_number": act_number,
                    "ministry": ministry,
                    "keywords": keywords,
                    "section_type": section_type,
                    "document_label": doc_label,
                    "document_id": f"indiacode_{act_handle}_{section_type}",
                    "jurisdiction": "India",
                    "court": "Parliament of India",
                    "date": act_year,
                    "page_number": i + 1,
                })
                documents.append(page)
    
    logger.info(f"Loaded {len(documents)} pages from {len(act_dirs)} India Code acts")
    return documents
