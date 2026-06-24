"""
Entry point for the Legal RAG Chatbot web application.
Run with: python run.py
"""

import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app.config import FLASK_DEBUG, FLASK_HOST, FLASK_PORT
from app.main import create_app

if __name__ == "__main__":
    app = create_app()
    
    print("\n" + "=" * 60)
    print("  Legal RAG Chatbot")
    print("  Running on http://0.0.0.0:5001")
    print("=" * 60)
    print("\n")
    
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=True,
    )
