"""
CLI script to test queries against the Legal RAG pipeline.

Usage:
    python scripts/test_query.py "What are the fundamental rights under the Indian Constitution?"
    python scripts/test_query.py --interactive
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_query")


def main():
    parser = argparse.ArgumentParser(description="Test queries against the Legal RAG pipeline")
    parser.add_argument(
        "question",
        nargs="?",
        help="Legal question to ask",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive Q&A session",
    )
    args = parser.parse_args()
    
    # Initialize the chain
    logger.info("Initializing Legal RAG Chain (this may take a moment)...")
    from rag.chain import LegalRAGChain
    chain = LegalRAGChain()
    logger.info("Chain initialized. Ready for queries.\n")
    
    if args.interactive:
        _interactive_mode(chain)
    elif args.question:
        _single_query(chain, args.question)
    else:
        parser.print_help()


def _single_query(chain, question: str):
    """Process a single question and print the response."""
    print(f"\n{'=' * 60}")
    print(f"Question: {question}")
    print(f"{'=' * 60}\n")
    
    response = chain.ask(question, session_id="test_cli")
    
    print(f"\n{'─' * 60}")
    print("Response:")
    print(f"{'─' * 60}\n")
    print(response)
    print(f"\n{'=' * 60}")


def _interactive_mode(chain):
    """Start an interactive Q&A session."""
    session_id = "interactive_cli"
    
    print(f"\n{'=' * 60}")
    print("Legal RAG Chatbot — Interactive Mode")
    print("Type 'quit' or 'exit' to stop, 'new' to start a new chat")
    print(f"{'=' * 60}\n")
    
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not question:
            continue
        
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        
        if question.lower() == "new":
            chain.new_chat(session_id)
            print("--- Chat history cleared ---")
            continue
        
        response = chain.ask(question, session_id=session_id)
        print(f"\nAssistant: {response}")


if __name__ == "__main__":
    main()
