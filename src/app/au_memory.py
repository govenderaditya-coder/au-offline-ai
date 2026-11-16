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
        """
        Recalls relevant memories using Dify-inspired Reciprocal Rank Fusion (RRF).
        Combines SQLite FTS5 BM25 keyword rankings with semantic token-overlap and recency scores:
        Score(d) = (1.0 / (60 + rank_fts)) + (0.8 / (60 + rank_semantic)) + (0.4 / (60 + rank_recency))
        """
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip().lower()
        if not clean_query:
            return self.list_all(limit=limit)

        query_tokens = set(w for w in clean_query.split() if len(w) > 2)
        all_memories: List[Dict[str, Any]] = []

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, user_id, fact, category, confidence, created_at, last_accessed_at, access_count FROM memories")
            all_memories = [dict(row) for row in cur.fetchall()]

        if not all_memories:
            return []

        # 1. Ranker A: FTS5 BM25 Keyword Search
        fts_rank_map: Dict[int, int] = {}
        if query_tokens:
            fts_query = " OR ".join([f'"{w}"*' for w in list(query_tokens)[:8]])
            try:
                with self._get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT m.id, rank
                        FROM fts_memories f
                        JOIN memories m ON f.rowid = m.id
                        WHERE fts_memories MATCH ?
                        ORDER BY rank
                        LIMIT 20
                    """, (fts_query,))
                    for rank_idx, row in enumerate(cur.fetchall()):
                        fts_rank_map[row["id"]] = rank_idx + 1
            except Exception:
                pass

        # 2. Ranker B: Semantic Token-Overlap (Jaccard similarity on tokens & character n-grams)
        semantic_scores: List[tuple[int, float]] = []
        for m in all_memories:
            fact_tokens = set(re.sub(r'[^\w\s]', ' ', m["fact"].lower()).split())
            overlap = query_tokens.intersection(fact_tokens)
            score = len(overlap) / (len(query_tokens) + 1.0) if query_tokens else 0.0
            # Bonus if exact substring appears
            if clean_query in m["fact"].lower():
                score += 1.0
            semantic_scores.append((m["id"], score))
        semantic_scores.sort(key=lambda x: x[1], reverse=True)
        semantic_rank_map = {item[0]: idx + 1 for idx, item in enumerate(semantic_scores)}

        # 3. Ranker C: Recency & Frequency
        recency_sorted = sorted(all_memories, key=lambda x: (x["access_count"], x["created_at"]), reverse=True)
        recency_rank_map = {m["id"]: idx + 1 for idx, m in enumerate(recency_sorted)}

        # 4. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[int, float] = {}
        K = 60.0
        for m in all_memories:
            mid = m["id"]
            score = 0.0
            if mid in fts_rank_map:
                score += 1.0 / (K + fts_rank_map[mid])
            if mid in semantic_rank_map:
                score += 0.8 / (K + semantic_rank_map[mid])
            if mid in recency_rank_map:
                score += 0.4 / (K + recency_rank_map[mid])
            rrf_scores[mid] = score

        # Sort memories by fused RRF score
        memory_dict = {m["id"]: m for m in all_memories}
        top_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:limit]
        final_results = [memory_dict[i] for i in top_ids if rrf_scores[i] > 0]

        # Update access tracking
        with self._get_conn() as conn:
            cur = conn.cursor()
            for r in final_results:
                cur.execute("UPDATE memories SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?", (r["id"],))
            conn.commit()

        return final_results

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
