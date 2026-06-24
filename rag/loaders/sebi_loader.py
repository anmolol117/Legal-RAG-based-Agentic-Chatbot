"""
Loader for SEBI Instructions.
Walks SEBI category directories (circulars, acts, regulations, guidelines, etc.),
reads metadata.json per item, and loads PDF attachments using PyMuPDFLoader.
"""

import json
import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# SEBI category subdirectories to process
SEBI_CATEGORIES = [
    "acts",
    "circulars",
    "general-orders",
    "guidelines",
    "master-circulars",
    "regulations",
    "rules",
]


def load_sebi_instructions(sebi_dir: Path, limit: int = None) -> List[Document]:
    """
    Load SEBI Instructions from the scraped data directory.
    
    Args:
        sebi_dir: Path to the SEBI Instructions directory.
        limit: Maximum number of items to process across all categories (None = all).
        
    Returns:
        List of LangChain Documents with SEBI metadata.
    """
    if not sebi_dir.exists():
        logger.warning(f"SEBI Instructions directory not found at {sebi_dir}")
        return []
    
    documents = []
    item_count = 0
    
    for category in SEBI_CATEGORIES:
        category_dir = sebi_dir / category
        if not category_dir.exists():
            logger.debug(f"SEBI category directory not found: {category_dir}")
            continue
        
        item_dirs = sorted([d for d in category_dir.iterdir() if d.is_dir()])
        logger.info(f"Processing {len(item_dirs)} items in SEBI/{category}")
        
        for item_dir in item_dirs:
            if limit and item_count >= limit:
                break
            
            metadata_file = item_dir / "metadata.json"
            if not metadata_file.exists():
                continue
            
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read metadata from {metadata_file}: {e}")
                continue
            
            title = meta.get("title", "")
            date = meta.get("date", "")
            sebi_category = meta.get("category", category)
            item_id = item_dir.name
            doc_id = f"sebi_{category}_{item_id}"
            
            base_metadata = {
                "source_type": "sebi_instruction",
                "document_id": doc_id,
                "title": title,
                "date": date,
                "category": sebi_category,
                "court": "Securities and Exchange Board of India",
                "jurisdiction": "India",
            }
            
            # Load PDF attachments
            attachments = meta.get("attachments", [])
            for attachment in attachments:
                relative_path = attachment.get("relative_path", "")
                if not relative_path:
                    continue
                
                pdf_path = item_dir / relative_path
                if not pdf_path.exists():
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
                        **base_metadata,
                        "attachment_label": attachment.get("label", ""),
                        "page_number": i + 1,
                    })
                    documents.append(page)
            
            item_count += 1
        
        if limit and item_count >= limit:
            break
    
    logger.info(f"Loaded {len(documents)} documents from {item_count} SEBI items")
    return documents
