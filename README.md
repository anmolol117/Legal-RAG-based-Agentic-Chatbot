# Legal RAG Agentic Chatbot

A professional, retrieval-augmented generation (RAG) powered chatbot specialized in Indian law. This system uses advanced semantic chunking, multi-query retrieval, and cross-encoder reranking to provide highly accurate, source-backed answers to legal queries.

<img width="1512" height="799" alt="Screenshot 2026-06-24 at 3 55 39 PM" src="https://github.com/user-attachments/assets/821220f2-33c6-4592-94a1-3b201829b017" />

## Data Sources 

* India Code: https://www.indiacode.nic.in
* Constitution: https://cdnbbsr.s3waas.gov.in/s380537a945c7aaa788ccfcdf1b99b5d8f/uploads/2024/07/20240716890312078.pdf
* Supreme Court Judgments: https://www.kaggle.com/datasets/vangap/indian-supreme-court-judgments/data
* RBI Circulars: https://www.rbi.org.in
* SEBI Regulations: https://www.sebi.gov.in/legal.html

## Architecture

*   **LLM:** Local `gemma4:12b-mlx` (via Ollama & `langchain-ollama`)
*   **Embeddings:** BAAI/bge-m3 (`langchain-huggingface`)
*   **Reranker:** BAAI/bge-reranker-v2-m3 (`CrossEncoderReranker`)
*   **Agent Framework:** LangGraph ReAct Agent
*   **Memory / State:** Persistent SQLite Checkpointer (`langgraph-checkpoint-sqlite`)
*   **Vector Database:** ChromaDB (`langchain-chroma`)
*   **Web Framework:** Flask

## Features

*   **Structure-Aware Chunking:** Parses legal documents intelligently, separating headers, sections, parts, and chapters.
*   **Two-Stage Retrieval:** Uses MultiQuery to expand user intent and CrossEncoder to rerank documents for maximum precision.
*   **Agentic Search:** If the knowledge base does not contain the answer or recent updates are needed, the agent seamlessly falls back to searching the live web using DuckDuckGo.
*   **Persistent Multi-Session History:** A ChatGPT-style sidebar allows you to manage multiple chats seamlessly. Your conversations are backed up locally using browser `localStorage` (for UI restoration) and an SQLite database (for the AI's contextual memory), meaning you can safely restart your server without losing your chat context.
*   **Apple-Inspired UI:** A sleek, clean, light-themed interface utilizing native macOS/iOS typography, frosted glassmorphism, and soft drop shadows that natively renders Markdown and citations.

## Evaluation

The pipeline was evaluated on a 50-query benchmark spanning the Constitution, Supreme Court judgments, RBI circulars, and SEBI regulations. Each query was scored on four binary (0/1) RAG metrics using an LLM-as-judge over the retrieved chunks and the generated answer.

| Metric | Pass Rate | What it measures |
| --- | --- | --- |
| Context Recall | 78% | Retrieved chunks contain the information needed to answer |
| Context Precision | 82% | Retrieved chunks are on-topic rather than noise |
| Faithfulness | 94% | The answer is grounded in the retrieved chunks (no hallucination) |
| Answer Relevance | 90% | The answer directly addresses the question asked |
| **Overall (avg)** | **86%** | |

**Notes:**

*   39 of 50 queries scored a perfect 1/1/1/1.
*   The two generation metrics (Faithfulness, Answer Relevance) are strong; when retrieval fails, the model reliably refuses ("the provided legal sources do not contain sufficient information") instead of hallucinating.
*   Only 3 queries scored Faithfulness = 0 — cases where retrieval returned off-topic chunks and the model answered correctly from prior knowledge rather than from context. Excluding these, faithfulness on non-hallucinating responses is effectively 100%.
*   The remaining ceiling is retrieval quality (Recall/Precision), not generation: a stronger retriever would lift those scores and let the correct-but-ungrounded answers become grounded.

## Setup Instructions

1.  **Activate the Virtual Environment:**
    ```bash
    source venv/bin/activate
    ```

2.  **Ensure Dependencies are Installed:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Ensure Ollama is Running:**
    You must have [Ollama](https://ollama.com/) installed and running locally with the `gemma4:12b-mlx` model pulled:
    ```bash
    ollama run gemma4:12b-mlx
    ```

4.  **Data Ingestion:**
    The project comes with an ingestion script. To ingest all data sources, run:
    ```bash
    python scripts/ingest.py --source all --reset
    ```
    *Note: The first time you run this, it will download the embedding models (~1.2GB) from HuggingFace.*

5.  **Testing the System:**
    You can test the RAG pipeline via CLI before starting the web server:
    ```bash
    python scripts/test_query.py "What does the Constitution of India say about Fundamental Rights?"
    ```

6.  **Start the Web UI:**
    Run the Flask server:
    ```bash
    python run.py
    ```
    Open your browser and navigate to `http://localhost:5001`.

## Project Structure

*   `app/`: Web interface (Flask, HTML, CSS, JS)
*   `rag/`: Core RAG logic (LangGraph, Retriever, Loaders, Embeddings, SQLite Memory)
*   `scripts/`: Utilities for data ingestion and CLI testing
*   `chroma_db/`: Local vector database store and SQLite checkpoints
*   `Data Sources/`: Directory where the raw PDF documents are stored.

## Legal Disclaimer
This tool provides legal information and research assistance based on the provided documents. It does not provide professional or personalized legal advice.
