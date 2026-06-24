"""
Loader for Supreme Court Judgments.
Parses judgments.csv for metadata and loads judgment PDFs using PyMuPDFLoader.
"""

import logging
from pathlib import Path
from typing import List

import pandas as pd
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _normalize_pdf_filename(temp_link: str) -> str:
    """
    Convert the temp_link column value to the actual PDF filename on disk.
    Example: 'supremecourt/2021/5/5_2021_36_1501_28814_Judgement_23-Jul-2021.pdf'
    becomes: '-0___jonew__judis__XXXXX.pdf' pattern — but the actual mapping
    uses the judis ID from the PDFs directory.
    
    Since the CSV temp_link doesn't directly map to filenames on disk,
    we'll match via the diary_no or load all PDFs independently.
    """
    # The temp_link contains the path like:
    # supremecourt/2021/5/5_2021_36_1501_28814_Judgement_23-Jul-2021.pdf
    # We extract what we can for metadata but load PDFs independently
    return temp_link


def load_sc_judgments(sc_dir: Path, limit: int = None) -> List[Document]:
    """
    Load Supreme Court Judgments from CSV metadata and PDFs.
    
    Args:
        sc_dir: Path to the Supreme Court Judgement Dataset directory.
        limit: Maximum number of judgment PDFs to load (None = all).
        
    Returns:
        List of LangChain Documents with judgment metadata.
    """
    if not sc_dir.exists():
        logger.warning(f"SC Judgments directory not found at {sc_dir}")
        return []
    
    csv_path = sc_dir / "judgments.csv"
    pdfs_dir = sc_dir / "pdfs"
    
    # Load CSV metadata into a lookup dict
    csv_metadata = {}
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines="skip")
            for _, row in df.iterrows():
                diary_no = str(row.get("diary_no", "")).strip()
                if diary_no:
                    csv_metadata[diary_no] = {
                        "case_no": str(row.get("case_no", "")),
                        "petitioner": str(row.get("pet", "")),
                        "respondent": str(row.get("res", "")),
                        "petitioner_advocate": str(row.get("pet_adv", "")),
                        "respondent_advocate": str(row.get("res_adv", "")),
                        "bench": str(row.get("bench", "")),
                        "judgment_by": str(row.get("judgement_by", "")),
                        "judgment_date": str(row.get("judgment_dates", "")),
                        "judgment_type": str(row.get("Judgement_type", "")),
                    }
            logger.info(f"Loaded metadata for {len(csv_metadata)} judgments from CSV")
        except Exception as e:
            logger.warning(f"Failed to parse judgments.csv: {e}")
    
    # Load PDFs
    documents = []
    if not pdfs_dir.exists():
        logger.warning(f"SC Judgments PDFs directory not found at {pdfs_dir}")
        return documents
    
    pdf_files = sorted(pdfs_dir.glob("*.pdf"))
    if limit:
        pdf_files = pdf_files[:limit]
    
    logger.info(f"Loading {len(pdf_files)} SC Judgment PDFs from {pdfs_dir}")
    
    for pdf_path in pdf_files:
        try:
            loader = PyMuPDFLoader(str(pdf_path))
            pages = loader.load()
        except Exception as e:
            logger.warning(f"Failed to load PDF {pdf_path}: {e}")
            continue
        
        # Extract a judis ID from filename for document_id
        # Filename pattern: -0___jonew__judis__XXXXX.pdf
        filename = pdf_path.stem
        judis_id = filename.split("__")[-1] if "__" in filename else filename
        doc_id = f"sc_judgment_{judis_id}"
        
        for i, page in enumerate(pages):
            if len(page.page_content.strip()) < 50:
                continue
            
            page.metadata.update({
                "source_type": "sc_judgment",
                "document_id": doc_id,
                "court": "Supreme Court of India",
                "jurisdiction": "India",
                "title": f"SC Judgment {judis_id}",
                "page_number": i + 1,
            })
            documents.append(page)
    
    logger.info(f"Loaded {len(documents)} pages from {len(pdf_files)} SC Judgment PDFs")
    return documents
