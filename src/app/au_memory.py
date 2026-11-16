#!/usr/bin/env python3
"""
AU Mem0 Offline Personal Memory Engine
Provides long-term episodic, semantic, and preference memory for AU.
Uses local SQLite with FTS5 full-text search and background fact extraction.
"""

import os
import sys
import re
import json
import sqlite3
import urllib.request
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.expanduser("~/.offline-ai")
DB_PATH = os.path.join(DB_DIR, "memory.db")

os.makedirs(DB_DIR, exist_ok=True)

class AUMemoryEngine:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # Main memories table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    fact TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1
                )
            """)
            # FTS5 full-text search table for instant zero-dependency semantic search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
                    fact,
                    category,
                    content='memories',
                    content_rowid='id'
                )
            """)
            # Triggers to keep FTS in sync with main table
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO fts_memories(rowid, fact, category) VALUES (new.id, new.fact, new.category);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO fts_memories(fts_memories, rowid, fact, category) VALUES('delete', old.id, old.fact, old.category);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO fts_memories(fts_memories, rowid, fact, category) VALUES('delete', old.id, old.fact, old.category);
                    INSERT INTO fts_memories(rowid, fact, category) VALUES (new.id, new.fact, new.category);
                END;
            """)
            conn.commit()

    def store_fact(self, fact: str, category: str = "general", confidence: float = 1.0, user_id: str = "default_user") -> int:
        """Stores a new fact or updates existing if very similar."""
        fact_clean = fact.strip()
        if not fact_clean or len(fact_clean) < 3:
            return -1

        # Check for duplicate
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, access_count FROM memories WHERE lower(fact) = lower(?)", (fact_clean,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (existing["id"],)
                )
                conn.commit()
                return existing["id"]

            cur.execute(
                "INSERT INTO memories (user_id, fact, category, confidence) VALUES (?, ?, ?, ?)",
                (user_id, fact_clean, category.lower(), confidence)
            )
            new_id = cur.lastrowid
            conn.commit()
            return new_id

    def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Recalls relevant memories using FTS5 search with fallback to recent facts."""
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
        results = []

        with self._get_conn() as conn:
            cur = conn.cursor()

            # 1. Try full-text search match if query words exist
            words = [w for w in clean_query.split() if len(w) > 2]
            if words:
                fts_query = " OR ".join([f'"{w}"*' for w in words[:6]])
                try:
                    cur.execute("""
                        SELECT m.id, m.fact, m.category, m.created_at, rank
                        FROM fts_memories f
                        JOIN memories m ON f.rowid = m.id
                        WHERE fts_memories MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """, (fts_query, limit))
                    results = [dict(row) for row in cur.fetchall()]
                except Exception:
                    pass

            # 2. If fewer than limit, supplement with most frequently accessed recent facts
            if len(results) < limit:
                needed = limit - len(results)
                existing_ids = [r["id"] for r in results]
                placeholders = ",".join(["?"] * len(existing_ids)) if existing_ids else "-1"
                sql = f"""
                    SELECT id, fact, category, created_at
                    FROM memories
                    WHERE id NOT IN ({placeholders})
                    ORDER BY access_count DESC, created_at DESC
                    LIMIT ?
                """
                args = existing_ids + [needed] if existing_ids else [needed]
                cur.execute(sql, args)
                supplemental = [dict(row) for row in cur.fetchall()]
                results.extend(supplemental)

            # Update access counts for recalled memories
            for r in results:
                cur.execute("UPDATE memories SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?", (r["id"],))
            conn.commit()

        return results

    def list_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists all stored memories ordered by recency."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, fact, category, access_count, created_at FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def delete_fact(self, memory_id: int) -> bool:
        """Deletes a memory by ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_all(self):
        """Clears all stored memories."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()

    def format_context_prompt(self, user_query: str) -> str:
        """Formats recalled memories into a system prompt injection block."""
        memories = self.recall(user_query, limit=4)
        if not memories:
            return ""

        facts_list = "\n".join([f"- {m['fact']}" for m in memories])
        return (
            "\n[RECALLED PERSONAL CONTEXT & MEMORIES]:\n"
            f"{facts_list}\n"
            "(Use these remembered facts naturally when relevant, but do not recite them verbatim unless asked.)\n"
        )

# ==============================================================================
# Fast Heuristic & Local Fact Extractor
# ==============================================================================

# Regex patterns for high-confidence spontaneous facts
FACT_PATTERNS = [
    (r"(?:my name is|call me|i am) ([a-zA-Z\s]{2,25})", "User's name is {0}", "identity"),
    (r"(?:i live in|i'm based in|my location is) ([a-zA-Z\s,]{2,40})", "User lives in {0}", "location"),
    (r"(?:i prefer|i like|always use) ([a-zA-Z0-9\s_\-\.]{2,40}) (?:for|when|over)", "User prefers {0}", "preference"),
    (r"(?:my favorite|i love) ([a-zA-Z0-9\s_\-\.]{2,40})", "User's favorite is {0}", "preference"),
    (r"(?:remember that|note that|keep in mind that) (.*)", "User requested to remember: {0}", "explicit"),
    (r"(?:my email is) ([a-zA-Z0-9_\-\.]+@[a-zA-Z0-9_\-\.]+)", "User email is {0}", "contact"),
]

def extract_and_store_facts(user_speech: str, memory_engine: Optional[AUMemoryEngine] = None) -> List[str]:
    """Extracts facts from user input and saves them to memory."""
    engine = memory_engine or AUMemoryEngine()
    saved = []

    # 1. Regex Fast-Path (instant, zero compute overhead)
    for pattern, template, cat in FACT_PATTERNS:
        m = re.search(pattern, user_speech, re.IGNORECASE)
        if m:
            extracted_val = m.group(1).strip()
            fact_str = template.format(extracted_val)
            fid = engine.store_fact(fact_str, category=cat)
            if fid > 0:
                saved.append(fact_str)

    return saved

if __name__ == "__main__":
    mem = AUMemoryEngine()
    print("Initializing AU Memory Engine...")

    # Seed baseline if empty
    all_m = mem.list_all()
    if not all_m:
        mem.store_fact("User's name is Aditya", category="identity")
        mem.store_fact("User's primary computer is a MacBook Air M4 with 16GB RAM", category="hardware")
        mem.store_fact("User prefers dark mode and local offline AI", category="preference")
        mem.store_fact("User is building AU Offline AI personal assistant", category="project")
        print("Seeded default memory profile.")

    print(f"\nTotal Memories Stored: {len(mem.list_all())}")
    for m in mem.list_all()[:5]:
        print(f"  [{m['id']}] ({m['category']}): {m['fact']}")

    test_q = "What laptop do I have and what are we building?"
    print(f"\nTest Query: '{test_q}'")
    print("Recalled Prompt Block:")
    print(mem.format_context_prompt(test_q))
