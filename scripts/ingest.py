"""
CLI script to ingest legal data sources into the ChromaDB vector store.

Usage:
    python scripts/ingest.py --source all
    python scripts/ingest.py --source constitution --limit 5
    python scripts/ingest.py --source rbi --limit 10 --reset
"""

import argparse
import logging
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tqdm import tqdm

from app.config import (
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    CONSTITUTION_DIR,
    EMBEDDING_MODEL_NAME,
    GOOGLE_API_KEY,
    INDIA_CODE_DIR,
    LLM_MODEL_NAME,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    CHUNK_OVERLAP,
    RBI_CIRCULARS_DIR,
    SC_JUDGMENTS_DIR,
    SEBI_INSTRUCTIONS_DIR,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest")


def main():
    parser = argparse.ArgumentParser(description="Ingest legal data sources into ChromaDB")
    parser.add_argument(
        "--source",
        choices=["all", "constitution", "indiacode", "sc", "rbi", "sebi"],
        default="all",
        help="Which data source to ingest (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of documents/items per source (for testing)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset (delete and recreate) the ChromaDB collection before ingesting",
    )
    parser.add_argument(
        "--no-enhanced-chunks",
        action="store_true",
        help="Skip generation of enhanced chunks (summaries, keywords) to save time",
    )
    args = parser.parse_args()
    
    start_time = time.time()
    
    # --- Step 1: Initialize embedding model ---
    logger.info("=" * 60)
    logger.info("LEGAL RAG INGESTION PIPELINE")
    logger.info("=" * 60)
    
    from rag.embeddings import get_embedding_model
    embedding_model = get_embedding_model(EMBEDDING_MODEL_NAME)
    
    # --- Step 2: Initialize vector store ---
    from rag.vectorstore import (
        add_documents_to_vectorstore,
        get_vectorstore,
        reset_vectorstore,
    )
    
    if args.reset:
        logger.info("Resetting ChromaDB collection...")
        vectorstore = reset_vectorstore(embedding_model, CHROMA_DB_DIR, CHROMA_COLLECTION_NAME)
    else:
        vectorstore = get_vectorstore(embedding_model, CHROMA_DB_DIR, CHROMA_COLLECTION_NAME)
    
    # --- Step 3: Initialize chunker ---
    from rag.chunking.legal_chunker import LegalChunker
    
    llm = None
    if not args.no_enhanced_chunks:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL_NAME,
            google_api_key=GOOGLE_API_KEY,
            temperature=0,
        )
    
    chunker = LegalChunker(
        max_chunk_size=MAX_CHUNK_SIZE,
        min_chunk_size=MIN_CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        generate_enhanced_chunks=not args.no_enhanced_chunks,
        llm=llm,
    )
    
    # --- Step 4: Load and process each source ---
    sources_to_process = []
    
    if args.source in ("all", "constitution"):
        sources_to_process.append(("constitution", "Constitution of India"))
    if args.source in ("all", "indiacode"):
        sources_to_process.append(("indiacode", "India Code Central Acts"))
    if args.source in ("all", "sc"):
        sources_to_process.append(("sc", "Supreme Court Judgments"))
    if args.source in ("all", "rbi"):
        sources_to_process.append(("rbi", "RBI Circulars"))
    if args.source in ("all", "sebi"):
        sources_to_process.append(("sebi", "SEBI Instructions"))
    
    total_documents = 0
    total_chunks = 0
    
    for source_key, source_name in sources_to_process:
        logger.info(f"\n{'─' * 50}")
        logger.info(f"Processing: {source_name}")
        logger.info(f"{'─' * 50}")
        
        # Load documents
        documents = _load_source(source_key, args.limit)
        
        if not documents:
            logger.warning(f"No documents loaded for {source_name}")
            continue
        
        logger.info(f"Loaded {len(documents)} raw documents from {source_name}")
        total_documents += len(documents)
        
        # Chunk documents
        logger.info(f"Chunking {len(documents)} documents...")
        chunks = chunker.chunk_documents(documents)
        logger.info(f"Created {len(chunks)} chunks from {source_name}")
        total_chunks += len(chunks)
        
        # Add to vector store
        logger.info(f"Adding {len(chunks)} chunks to ChromaDB...")
        add_documents_to_vectorstore(vectorstore, chunks, batch_size=50)
        logger.info(f"✓ {source_name} ingested successfully")
    
    # --- Summary ---
    elapsed = time.time() - start_time
    logger.info(f"\n{'=' * 60}")
    logger.info("INGESTION COMPLETE")
    logger.info(f"{'=' * 60}")
    logger.info(f"Total raw documents loaded: {total_documents}")
    logger.info(f"Total chunks created:       {total_chunks}")
    logger.info(f"Time elapsed:               {elapsed:.1f} seconds")
    logger.info(f"ChromaDB directory:         {CHROMA_DB_DIR}")
    logger.info(f"{'=' * 60}")


def _load_source(source_key: str, limit: int = None):
    """Load documents from a specific source."""
    
    if source_key == "constitution":
        from rag.loaders.constitution_loader import load_constitution
        return load_constitution(CONSTITUTION_DIR, limit=limit)
    
    elif source_key == "indiacode":
        from rag.loaders.indiacode_loader import load_indiacode
        return load_indiacode(INDIA_CODE_DIR, limit=limit)
    
    elif source_key == "sc":
        from rag.loaders.sc_judgments_loader import load_sc_judgments
        return load_sc_judgments(SC_JUDGMENTS_DIR, limit=limit)
    
    elif source_key == "rbi":
        from rag.loaders.rbi_loader import load_rbi_circulars
        return load_rbi_circulars(RBI_CIRCULARS_DIR, limit=limit)
    
    elif source_key == "sebi":
        from rag.loaders.sebi_loader import load_sebi_instructions
        return load_sebi_instructions(SEBI_INSTRUCTIONS_DIR, limit=limit)
    
    else:
        logger.warning(f"Unknown source: {source_key}")
        return []


if __name__ == "__main__":
    main()
