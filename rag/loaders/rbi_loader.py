"""
Loader for RBI Circulars.
Walks the RBI Circulars directory (organized by YYYY-MM/circular_id/),
reads metadata.json, and loads PDF attachments using PyMuPDFLoader.
"""

import json
import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def load_rbi_circulars(rbi_dir: Path, limit: int = None) -> List[Document]:
    """
    Load RBI Circulars from the scraped data directory.
    
    Args:
        rbi_dir: Path to the RBI Circulars directory.
        limit: Maximum number of circulars to process (None = all).
        
    Returns:
        List of LangChain Documents with circular metadata.
    """
    if not rbi_dir.exists():
        logger.warning(f"RBI Circulars directory not found at {rbi_dir}")
        return []
    
    documents = []
    circular_count = 0
    
    # Walk through month directories (2020-09, 2020-10, etc.)
    month_dirs = sorted([d for d in rbi_dir.iterdir() 
                         if d.is_dir() and not d.name.startswith(".")])
    
    logger.info(f"Scanning {len(month_dirs)} month directories in RBI Circulars")
    
    for month_dir in month_dirs:
        # Each month directory contains circular ID subdirectories
        circular_dirs = sorted([d for d in month_dir.iterdir() if d.is_dir()])
        
        for circular_dir in circular_dirs:
            if limit and circular_count >= limit:
                break
            
            metadata_file = circular_dir / "metadata.json"
            if not metadata_file.exists():
                continue
            
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read metadata from {metadata_file}: {e}")
                continue
            
            circular_id = meta.get("circular_id", circular_dir.name)
            title = meta.get("title", "")
            date = meta.get("date", "")
            department = meta.get("department", "")
            subject = meta.get("subject", "")
            meant_for = meta.get("meant_for", "")
            body_text = meta.get("body_text", "")
            
            doc_id = f"rbi_circular_{circular_id}"
            
            base_metadata = {
                "source_type": "rbi_circular",
                "document_id": doc_id,
                "title": title,
                "date": date,
                "department": department,
                "subject": subject,
                "meant_for": meant_for,
                "circular_id": circular_id,
                "court": "Reserve Bank of India",
                "jurisdiction": "India",
            }
            
            # Create a document from the body_text (inline text from the webpage)
            if body_text and len(body_text.strip()) > 50:
                doc = Document(
                    page_content=body_text,
                    metadata={**base_metadata, "content_source": "body_text"},
                )
                documents.append(doc)
            
            # Load PDF attachments
            attachments = meta.get("attachments", [])
            for attachment in attachments:
                relative_path = attachment.get("relative_path", "")
                if not relative_path:
                    continue
                
                pdf_path = circular_dir / relative_path
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
                        "content_source": "pdf_attachment",
                        "attachment_label": attachment.get("label", ""),
                        "page_number": i + 1,
                    })
                    documents.append(page)
            
            circular_count += 1
        
        if limit and circular_count >= limit:
            break
    
    logger.info(f"Loaded {len(documents)} documents from {circular_count} RBI Circulars")
    return documents
