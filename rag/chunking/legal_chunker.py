"""
Section-based Legal Document Chunker.

Instead of splitting documents into fixed-size token chunks, this module:
1. Detects legal document structure using regex-based heuristics
2. Creates section-based chunks (facts, issues, arguments, holdings, etc.)
3. Applies size constraints using LangChain's RecursiveCharacterTextSplitter
4. Generates retrieval-enhanced chunks (summaries, holdings, citations, keywords)
5. Attaches rich metadata to every chunk
"""

import hashlib
import logging
import re
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# --- Section Detection Patterns ---
# These regex patterns identify common legal document sections

JUDGMENT_SECTION_PATTERNS = [
    (r"(?i)^\s*(JUDGMENT|JUDGEMENT)\s*$", "judgment"),
    (r"(?i)^\s*(ORDER)\s*$", "order"),
    (r"(?i)^\s*(FACTS|FACTUAL\s+BACKGROUND|BRIEF\s+FACTS)\b", "facts"),
    (r"(?i)^\s*(ISSUES?\s*(FRAMED|FOR\s+CONSIDERATION|RAISED)?)\s*$", "issues"),
    (r"(?i)^\s*(ARGUMENTS?|SUBMISSIONS?|CONTENTIONS?)\b", "arguments"),
    (r"(?i)^\s*(ANALYSIS|REASONING|DISCUSSION|CONSIDERATION)\b", "analysis"),
    (r"(?i)^\s*(HELD|HOLDING|HELD\s+THAT)\b", "holding"),
    (r"(?i)^\s*(CONCLUSION|RESULT|DISPOSITION)\b", "conclusion"),
    (r"(?i)^\s*(WHEREAS)\b", "preamble"),
    (r"(?i)^\s*(PRAYER|RELIEF)\b", "prayer"),
]

STATUTE_SECTION_PATTERNS = [
    (r"(?i)^\s*PREAMBLE\b", "preamble"),
    (r"(?i)^\s*(CHAPTER|PART)\s+[IVXLCDM\d]+", "chapter"),
    (r"(?i)^\s*Section\s+\d+", "provisions"),
    (r"(?i)^\s*Article\s+\d+", "provisions"),
    (r"(?i)^\s*(SCHEDULE|APPENDIX)\b", "schedule"),
    (r"(?i)^\s*(DEFINITIONS?|INTERPRETATION)\b", "definitions"),
    (r"(?i)^\s*(SHORT\s+TITLE|PRELIMINARY)\b", "preliminary"),
    (r"(?i)^\s*(REPEAL|AMENDMENT|SAVING)\b", "repeal_amendment"),
]

REGULATORY_SECTION_PATTERNS = [
    (r"(?i)^\s*(SCOPE|APPLICABILITY)\b", "scope"),
    (r"(?i)^\s*(DEFINITIONS?)\b", "definitions"),
    (r"(?i)^\s*(DIRECTIONS?|INSTRUCTIONS?)\b", "directions"),
    (r"(?i)^\s*(GUIDELINES?)\b", "guidelines"),
    (r"(?i)^\s*(COMPLIANCE|REPORTING)\b", "compliance"),
    (r"(?i)^\s*(PENALTIES?|SANCTIONS?)\b", "penalties"),
    (r"(?i)^\s*(EFFECTIVE\s+DATE|COMMENCEMENT)\b", "effective_date"),
]

# Combined patterns for detection
ALL_SECTION_PATTERNS = (
    JUDGMENT_SECTION_PATTERNS
    + STATUTE_SECTION_PATTERNS
    + REGULATORY_SECTION_PATTERNS
)

# Citation patterns for extraction
CITATION_PATTERNS = [
    r"\(\d{4}\)\s+\d+\s+SCC\s+\d+",              # (2020) 5 SCC 123
    r"\d{4}\s+SCC\s+OnLine\s+SC\s+\d+",           # 2020 SCC OnLine SC 123
    r"AIR\s+\d{4}\s+SC\s+\d+",                     # AIR 2020 SC 123
    r"\[\d{4}\]\s+\d+\s+SCR\s+\d+",               # [2020] 5 SCR 123
    r"(?:Section|Sec\.?)\s+\d+[A-Za-z]?",          # Section 302, Sec. 420A
    r"Article\s+\d+[A-Za-z]?",                      # Article 21, Article 14
    r"(?:Act|Code)\s+(?:No\.?\s*)?\d+\s+of\s+\d{4}",  # Act No. 45 of 1860
    r"IPC|CrPC|CPC|IT\s+Act|Companies\s+Act",      # Common act abbreviations
]


def _generate_doc_id(content: str, metadata: dict) -> str:
    """Generate a unique document ID from content hash and metadata."""
    hash_input = f"{metadata.get('document_id', '')}-{content[:200]}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:12]


def _detect_sections(text: str, source_type: str) -> List[Tuple[str, str, int]]:
    """
    Detect section boundaries in text using regex patterns.
    
    Returns list of (section_type, section_header, line_index) tuples.
    """
    lines = text.split("\n")
    sections = []
    
    # Choose appropriate patterns based on source type
    if source_type in ("sc_judgment",):
        patterns = JUDGMENT_SECTION_PATTERNS + REGULATORY_SECTION_PATTERNS
    elif source_type in ("central_act", "constitution"):
        patterns = STATUTE_SECTION_PATTERNS + JUDGMENT_SECTION_PATTERNS
    else:
        patterns = ALL_SECTION_PATTERNS
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        for pattern, section_type in patterns:
            if re.match(pattern, stripped):
                sections.append((section_type, stripped, i))
                break
    
    return sections


def _extract_citations(text: str) -> List[str]:
    """Extract legal citations from text."""
    citations = set()
    for pattern in CITATION_PATTERNS:
        matches = re.findall(pattern, text)
        citations.update(matches)
    return sorted(citations)


def _split_into_sections(text: str, source_type: str) -> List[Dict]:
    """
    Split text into logical sections based on detected structure.
    
    Returns list of dicts with 'section_type', 'header', 'content'.
    """
    sections_detected = _detect_sections(text, source_type)
    lines = text.split("\n")
    
    if not sections_detected:
        # No sections detected — treat as a single "general" section
        return [{
            "section_type": "general",
            "header": "",
            "content": text,
        }]
    
    sections = []
    for i, (section_type, header, line_idx) in enumerate(sections_detected):
        # Determine the end of this section (start of next section, or end of text)
        if i + 1 < len(sections_detected):
            end_idx = sections_detected[i + 1][2]
        else:
            end_idx = len(lines)
        
        section_content = "\n".join(lines[line_idx:end_idx]).strip()
        
        if section_content:
            sections.append({
                "section_type": section_type,
                "header": header,
                "content": section_content,
            })
    
    # Handle any text before the first detected section
    first_section_line = sections_detected[0][2]
    if first_section_line > 0:
        preamble_content = "\n".join(lines[:first_section_line]).strip()
        if preamble_content and len(preamble_content) > 50:
            sections.insert(0, {
                "section_type": "metadata",
                "header": "Header/Preamble",
                "content": preamble_content,
            })
    
    return sections


class LegalChunker:
    """
    Section-based chunker for legal documents.
    
    Splits documents by logical legal sections, applies size constraints,
    and generates retrieval-enhanced chunks (summaries, citations, keywords).
    """
    
    def __init__(
        self,
        max_chunk_size: int = 6000,
        min_chunk_size: int = 100,
        chunk_overlap: int = 200,
        generate_enhanced_chunks: bool = True,
        llm=None,
    ):
        """
        Args:
            max_chunk_size: Maximum characters per chunk.
            min_chunk_size: Minimum characters per chunk (merge if smaller).
            chunk_overlap: Character overlap when sub-splitting oversized sections.
            generate_enhanced_chunks: Whether to generate summary/citation/keyword chunks.
            llm: LangChain LLM instance for generating enhanced chunks (optional).
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.chunk_overlap = chunk_overlap
        self.generate_enhanced_chunks = generate_enhanced_chunks
        self.llm = llm
        
        # LangChain's text splitter for oversized sections
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Process a list of LangChain Documents through the legal chunking pipeline.
        
        Groups pages by document_id, concatenates their text,
        then performs section-based chunking.
        
        Args:
            documents: List of raw documents (typically one per page).
            
        Returns:
            List of chunked documents with metadata.
        """
        # Group pages by document_id
        doc_groups: Dict[str, List[Document]] = {}
        for doc in documents:
            doc_id = doc.metadata.get("document_id", _generate_doc_id(doc.page_content, doc.metadata))
            if doc_id not in doc_groups:
                doc_groups[doc_id] = []
            doc_groups[doc_id].append(doc)
        
        logger.info(f"Chunking {len(doc_groups)} unique documents from {len(documents)} pages")
        
        all_chunks = []
        for doc_id, pages in doc_groups.items():
            # Sort pages by page number
            pages.sort(key=lambda d: d.metadata.get("page_number", 0))
            
            # Concatenate all pages into full document text
            full_text = "\n\n".join(p.page_content for p in pages)
            
            # Use metadata from the first page as base
            base_metadata = pages[0].metadata.copy()
            base_metadata.pop("page_number", None)
            
            # Chunk this document
            chunks = self._chunk_single_document(full_text, base_metadata)
            all_chunks.extend(chunks)
        
        logger.info(f"Created {len(all_chunks)} chunks from {len(doc_groups)} documents")
        return all_chunks
    
    def _chunk_single_document(self, text: str, metadata: dict) -> List[Document]:
        """
        Chunk a single document's full text into section-based chunks.
        """
        source_type = metadata.get("source_type", "general")
        doc_id = metadata.get("document_id", _generate_doc_id(text, metadata))
        
        # Step 1: Detect and split into logical sections
        sections = _split_into_sections(text, source_type)
        
        # Step 2: Apply size constraints and create chunks
        chunks = []
        chunk_index = 0
        
        for i, section in enumerate(sections):
            section_content = section["content"]
            section_type = section["section_type"]
            
            # Handle undersized sections: merge with next section
            if len(section_content) < self.min_chunk_size and i + 1 < len(sections):
                sections[i + 1]["content"] = section_content + "\n\n" + sections[i + 1]["content"]
                continue
            
            # Handle oversized sections: sub-split using RecursiveCharacterTextSplitter
            if len(section_content) > self.max_chunk_size:
                sub_docs = self.text_splitter.create_documents(
                    [section_content],
                    metadatas=[{
                        **metadata,
                        "section_type": section_type,
                        "section_header": section["header"],
                        "chunk_type": "section",
                        "parent_document_id": doc_id,
                    }],
                )
                for sub_doc in sub_docs:
                    sub_doc.metadata["chunk_index"] = chunk_index
                    chunks.append(sub_doc)
                    chunk_index += 1
            else:
                # Normal-sized section: create a single chunk
                chunk = Document(
                    page_content=section_content,
                    metadata={
                        **metadata,
                        "section_type": section_type,
                        "section_header": section["header"],
                        "chunk_type": "section",
                        "chunk_index": chunk_index,
                        "parent_document_id": doc_id,
                    },
                )
                chunks.append(chunk)
                chunk_index += 1
        
        # Step 3: Generate retrieval-enhanced chunks
        if self.generate_enhanced_chunks:
            enhanced = self._generate_enhanced_chunks(text, metadata, doc_id)
            chunks.extend(enhanced)
        
        return chunks
    
    def _generate_enhanced_chunks(
        self, text: str, metadata: dict, doc_id: str
    ) -> List[Document]:
        """
        Generate additional retrieval-focused chunks:
        - Summary chunk
        - Citation chunk
        - Keywords chunk
        """
        enhanced_chunks = []
        
        # --- Citation Chunk ---
        citations = _extract_citations(text)
        if citations:
            citation_text = "Legal Citations Referenced:\n" + "\n".join(f"- {c}" for c in citations)
            enhanced_chunks.append(Document(
                page_content=citation_text,
                metadata={
                    **metadata,
                    "chunk_type": "citation",
                    "section_type": "citations",
                    "parent_document_id": doc_id,
                    "chunk_index": -1,
                },
            ))
        
        # --- Summary Chunk (using LLM if available) ---
        if self.llm:
            try:
                # Truncate text for summarization to avoid token limits
                truncated_text = text[:8000]
                summary_prompt = (
                    "Summarize the following legal document in 3-5 sentences. "
                    "Focus on the key legal issue, the holding or main provision, "
                    "and the applicable law or regulation.\n\n"
                    f"Document:\n{truncated_text}\n\nSummary:"
                )
                summary = self.llm.invoke(summary_prompt)
                summary_text = summary.content if hasattr(summary, "content") else str(summary)
                
                enhanced_chunks.append(Document(
                    page_content=f"Document Summary: {summary_text}",
                    metadata={
                        **metadata,
                        "chunk_type": "summary",
                        "section_type": "summary",
                        "parent_document_id": doc_id,
                        "chunk_index": -2,
                    },
                ))
            except Exception as e:
                logger.warning(f"Failed to generate summary for {doc_id}: {e}")
        
        # --- Keywords Chunk (using LLM if available) ---
        if self.llm:
            try:
                truncated_text = text[:6000]
                keywords_prompt = (
                    "Extract the key legal topics, statutes, legal principles, "
                    "and important terms from the following legal document. "
                    "Return them as a comma-separated list.\n\n"
                    f"Document:\n{truncated_text}\n\nKeywords:"
                )
                keywords_result = self.llm.invoke(keywords_prompt)
                keywords_text = keywords_result.content if hasattr(keywords_result, "content") else str(keywords_result)
                
                enhanced_chunks.append(Document(
                    page_content=f"Key Legal Topics and Terms: {keywords_text}",
                    metadata={
                        **metadata,
                        "chunk_type": "keywords",
                        "section_type": "keywords",
                        "parent_document_id": doc_id,
                        "chunk_index": -3,
                    },
                ))
            except Exception as e:
                logger.warning(f"Failed to generate keywords for {doc_id}: {e}")
        
        return enhanced_chunks
