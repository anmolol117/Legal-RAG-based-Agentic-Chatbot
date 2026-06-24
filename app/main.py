"""
Flask web application for the Legal RAG Chatbot.
Provides API endpoints for chat, session management, and the web UI.
"""

import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

logger = logging.getLogger(__name__)

# Global reference to the RAG chain (initialized lazily)
_rag_chain = None


def _get_chain():
    """Lazily initialize the RAG chain."""
    global _rag_chain
    if _rag_chain is None:
        from rag.chain import LegalRAGChain
        _rag_chain = LegalRAGChain()
    return _rag_chain


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    CORS(app)
    
    # ---------------------------------------------------------------
    # Page Routes
    # ---------------------------------------------------------------
    @app.route("/")
    def index():
        """Serve the main chat page."""
        return render_template("index.html")
    
    # ---------------------------------------------------------------
    # API Routes
    # ---------------------------------------------------------------
    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Process a chat message.
        
        Request JSON: { "message": "...", "session_id": "..." }
        Response JSON: { "response": "..." }
        """
        data = request.get_json()
        
        if not data or "message" not in data:
            return jsonify({"error": "Missing 'message' field"}), 400
        
        message = data["message"].strip()
        session_id = data.get("session_id", "default")
        
        if not message:
            return jsonify({"error": "Empty message"}), 400
        
        try:
            chain = _get_chain()
            response = chain.ask(message, session_id=session_id)
            return jsonify({"response": response})
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return jsonify({
                "response": (
                    "I encountered an error processing your question. "
                    "Please try again or rephrase your query."
                ),
                "error": str(e),
            }), 500
    
    @app.route("/api/new-chat", methods=["POST"])
    def new_chat():
        """
        Clear the chat history for a session.
        
        Request JSON: { "session_id": "..." }
        """
        data = request.get_json() or {}
        session_id = data.get("session_id", "default")
        
        try:
            chain = _get_chain()
            chain.new_chat(session_id)
            return jsonify({"status": "ok", "message": "Chat history cleared"})
        except Exception as e:
            logger.error(f"New chat error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "Legal RAG Chatbot",
        })
    
    return app
