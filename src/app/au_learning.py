#!/usr/bin/env python3
"""
AU Self-Improvement & Continuous Learning Engine
Enables AU to learn from user corrections, preferences, and explicit instructions over time.
Stores learned operational rules and patterns in SQLite (~/.offline-ai/learning.db)
and automatically injects active rules into future prompts so AU never makes the same mistake twice.
"""

import os
import re
import sys
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.expanduser("~/.offline-ai")
DB_PATH = os.path.join(DB_DIR, "learning.db")
os.makedirs(DB_DIR, exist_ok=True)

CORRECTION_PATTERNS = [
    (r"(?:no|don't|do not),?\s*(?:use|do|make)\s+([^,;.]+),?\s*(?:use|prefer|instead do)\s+([^,;.]+)", "Replace {0} with {1}"),
    (r"(?:always|from now on|in the future)\s+([^,;.]+)", "Always {0}"),
    (r"(?:never|don't ever)\s+([^,;.]+)", "Never {0}"),
    (r"(?:i prefer|my preference is to)\s+([^,;.]+)", "User preference: {0}"),
    (r"(?:remember to|make sure to|be sure to)\s+([^,;.]+)", "Always ensure to {0}"),
    (r"(?:when writing code|when coding|for python|for swift)\s+([^,;.]+)", "Coding rule: {0}"),
]

class AULearningEngine:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learned_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule TEXT NOT NULL UNIQUE,
                    category TEXT DEFAULT 'general',
                    source TEXT DEFAULT 'auto_correction',
                    confidence REAL DEFAULT 1.0,
                    applied_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_rule(self, rule: str, category: str = "general", source: str = "explicit", confidence: float = 1.0) -> int:
        """Stores a new behavioral rule or preference."""
        clean_rule = rule.strip()
        if not clean_rule or len(clean_rule) < 4:
            return -1

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO learned_rules (rule, category, source, confidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(rule) DO UPDATE SET
                    applied_count = applied_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
            """, (clean_rule, category, source, confidence))
            conn.commit()
            return cur.lastrowid or 1

    def detect_and_learn_from_feedback(self, user_text: str) -> List[str]:
        """Scans conversational input for implicit corrections or explicit directives."""
        learned = []
        for pattern, template in CORRECTION_PATTERNS:
            m = re.search(pattern, user_text, re.IGNORECASE)
            if m:
                groups = m.groups()
                rule_str = template.format(*groups).strip()
                if rule_str and len(rule_str) > 5:
                    self.add_rule(rule_str, category="correction", source="chat_feedback")
                    learned.append(rule_str)
        return learned

    def list_rules(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns all active learned rules."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, rule, category, source, applied_count, created_at FROM learned_rules ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def delete_rule(self, rule_id: int) -> bool:
        """Removes a learned rule."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM learned_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_rules(self):
        """Clears all rules."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM learned_rules")
            conn.commit()

    def get_rules_prompt_injection(self) -> str:
        """Builds system prompt block containing active learned rules."""
        rules = self.list_rules(limit=10)
        if not rules:
            return ""

        rule_lines = "\n".join([f"- {r['rule']}" for r in rules])
        return (
            "\n[LEARNED BEHAVIORAL RULES & USER PREFERENCES]:\n"
            f"{rule_lines}\n"
            "(Strictly abide by these learned rules across all interactions.)\n"
        )

if __name__ == "__main__":
    learning = AULearningEngine()
    print("Initializing AU Learning Engine...")
    
    # Test adding default baseline rules if empty
    if not learning.list_rules():
        learning.add_rule("Always write clean, modular, typed Python code", category="coding", source="seed")
        learning.add_rule("Prefer surgical file edits over rewriting entire files", category="coding", source="seed")
        learning.add_rule("Always optimize for Apple Silicon M4 and unified memory", category="hardware", source="seed")

    # Test auto-detection
    test_feedback = "From now on always explain technical trade-offs before implementing changes"
    detected = learning.detect_and_learn_from_feedback(test_feedback)
    print("Auto-detected rules from user feedback:", detected)
    print("\nActive Learned Rules:")
    for r in learning.list_rules():
        print(f"  • [{r['category']}] {r['rule']}")
    print("\nInjection block:")
    print(learning.get_rules_prompt_injection())
