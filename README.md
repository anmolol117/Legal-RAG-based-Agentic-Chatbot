# Legal RAG Agentic Chatbot

A professional, retrieval-augmented generation (RAG) powered chatbot specialized in Indian law. This system uses advanced semantic chunking, multi-query retrieval, and cross-encoder reranking to provide highly accurate, source-backed answers to legal queries.

## Data Sources 

* India Code: https://www.indiacode.nic.in
* Constitution: https://cdnbbsr.s3waas.gov.in/s380537a945c7aaa788ccfcdf1b99b5d8f/uploads/2024/07/20240716890312078.pdf
* Supreme Court Judgments: https://www.kaggle.com/datasets/vangap/indian-supreme-court-judgments/data
* RBI Circulars: https://www.rbi.org.in
* SEBI Regulations: https://www.sebi.gov.in/legal.html

## Architecture

*   **LLM:** Local `llama3.1` (via Ollama & `langchain-ollama`)
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
    You must have [Ollama](https://ollama.com/) installed and running locally with the `llama3.1` model pulled:
    ```bash
    ollama run llama3.1
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
