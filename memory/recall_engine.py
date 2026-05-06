"""
Recall Engine — Intelligent memory retrieval for context injection.

Retrieves relevant memories across all layers and builds a coherent
context package for the current request. Supports keyword-based recall,
recency weighting, and importance scoring.
"""

import logging
from typing import Any

from memory.memory_index import memory_index
from memory.session_manager import session_manager

logger = logging.getLogger("presence.memory.recall_engine")


def recall_for_query(query: str, max_context_chars: int = 2000) -> str:
    """
    Recall relevant memories for a given query.

    Gathers context from:
    1. Active session (recent messages)
    2. Workspace facts (keyword match)
    3. Knowledge base (topic match)
    4. User preferences

    Returns a formatted context string for agent injection.
    """
    # Get recent session messages
    session_messages = session_manager.get_context(count=8)

    # Build rich context from all memory layers
    context = memory_index.build_context(session_messages, query=query)

    # Truncate if too long
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n[...memory truncated]"

    logger.debug(f"Recalled {len(context)} chars of context for query: {query[:50]}")
    return context


def extract_and_store_facts(user_text: str, ai_response: str):
    """
    Analyze a conversation turn and extract storable facts.

    Simple heuristic extraction — looks for self-statements,
    preferences, and named entities. No LLM call needed.
    """
    lower = user_text.lower()

    # Self-statements: "I am...", "My name is...", "I work at..."
    fact_patterns = [
        ("my name is ", "name"),
        ("i am ", "identity"),
        ("i work ", "work"),
        ("i live ", "location"),
        ("i like ", "preference"),
        ("i prefer ", "preference"),
        ("i love ", "preference"),
        ("i hate ", "preference"),
        ("i'm a ", "identity"),
        ("i want to ", "goal"),
        ("i need to ", "goal"),
        ("my favorite ", "preference"),
    ]

    for pattern, category in fact_patterns:
        if pattern in lower:
            # Extract the statement
            idx = lower.index(pattern)
            statement = user_text[idx:idx + len(pattern) + 100].strip()
            # Truncate at sentence boundary
            for end in ".!?\n":
                pos = statement.find(end)
                if pos > 0:
                    statement = statement[:pos + 1]
                    break
            if len(statement) > 10:
                memory_index.add_fact(statement, source=category)
                logger.info(f"Extracted fact ({category}): {statement[:60]}")


def store_interaction(user_text: str, ai_response: str, agent: str = "companion"):
    """Store a conversation turn in the active session and extract facts."""
    # Save to session
    session_manager.add_message("user", user_text)
    session_manager.add_message("assistant", ai_response, metadata={"agent": agent})

    # Auto-title the session from first user message
    session = session_manager.get_active_session()
    if session and len(session.messages) <= 2:
        session_manager.auto_title(user_text)

    # Extract and store facts
    extract_and_store_facts(user_text, ai_response)
