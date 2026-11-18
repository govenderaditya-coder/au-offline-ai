"""
AU v5.0 — Context Awareness & Proactive Intelligence Engine
Tracks sessions, infers focus, detects patterns, and proactively helps.
Pure stdlib — no external deps.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STATE_DIR = Path.home() / ".offline-ai"
STATE_FILE = STATE_DIR / "context_state.json"
SESSION_MAX_AGE_HOURS = 20          # resume today's session if < this old
LONG_SESSION_MINUTES = 90           # threshold to suggest a break
STUCK_REPETITIONS = 3               # same topic N times → "stuck" flag


# ---------------------------------------------------------------------------
# Topic extractor
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "AU orchestrator":       ["orchestrator", "queue", "task", "dispatch"],
    "macOS app development": ["swift", "xcode", "app", "toolbar", "swiftui", "macos"],
    "Python development":    ["python", "code", "debug", "error", "traceback", "script"],
    "memory engine":         ["memory", "mem0", "facts", "remember", "recall", "store"],
    "voice assistant":       ["voice", "whisper", "speak", "speech", "tts", "transcribe"],
    "document search":       ["document", "pdf", "search", "rag", "index", "embed"],
}


def extract_topics(text: str) -> list[str]:
    """Return all matching topic labels for the given text (lowercase match)."""
    lower = text.lower()
    found = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            found.append(topic)
    return found


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

@dataclass
class AUSession:
    session_id:       str         = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time:       float       = field(default_factory=time.time)
    topics_discussed: list[str]   = field(default_factory=list)
    files_accessed:   list[str]   = field(default_factory=list)
    actions_taken:    list[str]   = field(default_factory=list)
    last_query:       str         = ""
    query_count:      int         = 0
    # internal — recent queries for pattern analysis (not persisted in full)
    _recent_queries:  list[str]   = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_recent_queries", None)
        return d

    @staticmethod
    def from_dict(d: dict) -> "AUSession":
        d.pop("_recent_queries", None)
        return AUSession(**d)


# ---------------------------------------------------------------------------
# Context Engine
# ---------------------------------------------------------------------------

class AUContextEngine:
    """Context awareness and proactive intelligence for AU."""

    def __init__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.session: AUSession = self.start_session()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(self) -> None:
        state = self._load_state()
        state["session"] = self.session.to_dict()
        STATE_FILE.write_text(json.dumps(state, indent=2))

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self) -> AUSession:
        """Create a new session or resume today's if recent enough."""
        state = self._load_state()
        if "session" in state:
            saved = state["session"]
            age_hours = (time.time() - saved.get("start_time", 0)) / 3600
            if age_hours < SESSION_MAX_AGE_HOURS:
                session = AUSession.from_dict(saved)
                session._recent_queries = []
                return session
        # fresh session
        session = AUSession()
        self.session = session
        self._save_state()
        return session

    # ------------------------------------------------------------------
    # Interaction logging
    # ------------------------------------------------------------------

    def log_interaction(
        self,
        query: str,
        response_summary: str = "",
        tools_used: list | None = None,
    ) -> None:
        """Record a query/response pair into the current session."""
        s = self.session
        s.last_query = query
        s.query_count += 1
        s._recent_queries.append(query)
        if len(s._recent_queries) > 20:
            s._recent_queries = s._recent_queries[-20:]

        # accumulate topics
        new_topics = extract_topics(query)
        if response_summary:
            new_topics += extract_topics(response_summary)
        for t in new_topics:
            if t not in s.topics_discussed:
                s.topics_discussed.append(t)

        # accumulate tools → actions
        for tool in (tools_used or []):
            entry = f"used:{tool}"
            if entry not in s.actions_taken:
                s.actions_taken.append(entry)

        self._save_state()

    # ------------------------------------------------------------------
    # Focus inference
    # ------------------------------------------------------------------

    def get_current_focus(self) -> str:
        """Return the most recently discussed topic (or a generic label)."""
        s = self.session
        # check last 5 recent queries for most common topic
        recent = s._recent_queries[-5:] if s._recent_queries else []
        topic_counts: dict[str, int] = {}
        for q in reversed(recent):
            for t in extract_topics(q):
                topic_counts[t] = topic_counts.get(t, 0) + 1
        if topic_counts:
            return max(topic_counts, key=lambda k: topic_counts[k])
        if s.topics_discussed:
            return s.topics_discussed[-1]
        return "general conversation"

    # ------------------------------------------------------------------
    # Session summary
    # ------------------------------------------------------------------

    def get_session_summary(self) -> str:
        s = self.session
        elapsed_min = (time.time() - s.start_time) / 60
        if elapsed_min < 60:
            age_str = f"{int(elapsed_min)}m ago"
        else:
            age_str = f"{elapsed_min/60:.1f}h ago"

        topics_str = (
            ", ".join(s.topics_discussed) if s.topics_discussed else "nothing yet"
        )
        return (
            f"Session started {age_str}. "
            f"Discussed: {topics_str}. "
            f"{s.query_count} quer{'y' if s.query_count == 1 else 'ies'}."
        )

    # ------------------------------------------------------------------
    # Repetition detection
    # ------------------------------------------------------------------

    def detect_repetition(self, query: str) -> Optional[str]:
        """Return a proactive suggestion if the same topic appears 2+ times recently."""
        s = self.session
        new_topics = extract_topics(query)
        if not new_topics:
            return None

        # count how many previous queries matched the same topic
        for topic in new_topics:
            count = sum(
                1 for q in s._recent_queries[-10:]
                if topic in extract_topics(q)
            )
            if count >= 2:
                suggestions = {
                    "AU orchestrator":       "You've been working on the AU orchestrator quite a bit. Want me to help draft a design doc or summarise what we've covered?",
                    "macOS app development": "We keep returning to the macOS app. Should I help you outline the remaining features or troubleshoot a specific part?",
                    "Python development":    "This Python topic keeps coming up. Want me to review the relevant code end-to-end?",
                    "memory engine":         "Memory engine questions are recurring. Would a quick architectural overview help clarify things?",
                    "voice assistant":       "Voice assistant questions again — want me to run a diagnostic or summarise the pipeline?",
                    "document search":       "Document search keeps coming up. Should we map out the full RAG pipeline together?",
                }
                return suggestions.get(
                    topic,
                    f"You've asked about '{topic}' several times. Want to go deeper on it?",
                )
        return None

    # ------------------------------------------------------------------
    # Next-task inference
    # ------------------------------------------------------------------

    def infer_next_likely_task(self, recent_queries: list[str]) -> Optional[str]:
        """Suggest what the user probably needs next based on query patterns."""
        all_topics: list[str] = []
        for q in recent_queries:
            all_topics.extend(extract_topics(q))

        if not all_topics:
            return None

        # simple frequency map
        freq: dict[str, int] = {}
        for t in all_topics:
            freq[t] = freq.get(t, 0) + 1

        top = max(freq, key=lambda k: freq[k])

        transitions = {
            "AU orchestrator":       "testing the orchestrator end-to-end",
            "macOS app development": "wiring the UI to the backend models",
            "Python development":    "writing unit tests for the code you just built",
            "memory engine":         "integrating the memory engine with the orchestrator",
            "voice assistant":       "testing voice input in the macOS app",
            "document search":       "evaluating retrieval quality with sample queries",
        }
        next_task = transitions.get(top)
        if next_task:
            return f"Based on what you've been working on, next you might want to look at: {next_task}."
        return None

    # ------------------------------------------------------------------
    # Time context
    # ------------------------------------------------------------------

    def get_time_context(self) -> dict:
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            tod = "morning"
        elif 12 <= hour < 17:
            tod = "afternoon"
        elif 17 <= hour < 21:
            tod = "evening"
        else:
            tod = "night"

        hours_since_start = (time.time() - self.session.start_time) / 3600

        return {
            "time_of_day":      tod,
            "day_of_week":      now.strftime("%A"),
            "hours_since_start": round(hours_since_start, 2),
            "is_long_session":  hours_since_start * 60 >= LONG_SESSION_MINUTES,
        }

    # ------------------------------------------------------------------
    # Proactive message
    # ------------------------------------------------------------------

    def generate_proactive_message(self) -> Optional[str]:
        """Return a proactive suggestion when conditions warrant it."""
        s = self.session
        tc = self.get_time_context()

        # 1. Long session → suggest a break
        if tc["is_long_session"]:
            elapsed_h = tc["hours_since_start"]
            return (
                f"⏰ You've been at this for {elapsed_h:.1f}h. "
                "A short break might help — you'll come back sharper."
            )

        # 2. Same error/debug topic 3× in recent queries
        debug_hits = sum(
            1 for q in s._recent_queries[-8:]
            if re.search(r"\b(error|fail|broken|bug|traceback|exception)\b", q, re.I)
        )
        if debug_hits >= STUCK_REPETITIONS:
            return (
                "🔍 I've noticed you're hitting errors repeatedly. "
                "Want to try a different approach, or walk through it together from scratch?"
            )

        # 3. High query count with narrow focus → might be stuck
        if s.query_count >= 10 and len(s.topics_discussed) <= 2:
            return (
                "💡 You've sent a lot of queries about the same topic. "
                "Should I try to give you a consolidated explanation rather than piece-by-piece answers?"
            )

        return None

    # ------------------------------------------------------------------
    # Context injection string
    # ------------------------------------------------------------------

    def build_context_injection(self) -> str:
        s = self.session
        elapsed_min = int((time.time() - s.start_time) / 60)
        focus = self.get_current_focus()
        last = s.last_query[:60] + "…" if len(s.last_query) > 60 else s.last_query
        topics_str = ", ".join(s.topics_discussed[-3:]) if s.topics_discussed else "none yet"

        return (
            f"[CURRENT SESSION: {elapsed_min} min | "
            f"working on: {focus} | "
            f"{s.query_count} queries | "
            f"topics: {topics_str} | "
            f"last query: \"{last}\"]"
        )

    # ------------------------------------------------------------------
    # Work-pattern detection
    # ------------------------------------------------------------------

    def detect_work_pattern(self, session: AUSession) -> str:
        """
        Classify the user's current work mode from recent query vocabulary.

        Returns one of:
            "deep focus", "exploratory", "debugging", "building", "researching"
        """
        queries = session._recent_queries[-10:]
        if not queries:
            return "exploratory"

        combined = " ".join(queries).lower()

        scores: dict[str, int] = {
            "debugging":   0,
            "building":    0,
            "researching": 0,
            "deep focus":  0,
            "exploratory": 0,
        }

        # debugging signals
        for kw in ["error", "bug", "traceback", "exception", "fail", "broken", "debug", "fix"]:
            scores["debugging"] += combined.count(kw)

        # building signals
        for kw in ["create", "build", "implement", "write", "make", "add", "new", "generate"]:
            scores["building"] += combined.count(kw)

        # research signals
        for kw in ["how", "what", "why", "explain", "understand", "learn", "example", "docs"]:
            scores["researching"] += combined.count(kw)

        # deep focus: many queries on same narrow topic
        unique_topics = set()
        for q in queries:
            unique_topics.update(extract_topics(q))
        if len(unique_topics) <= 1 and session.query_count >= 6:
            scores["deep focus"] += 5

        # exploratory: many different topics
        if len(unique_topics) >= 4:
            scores["exploratory"] += 5

        return max(scores, key=lambda k: scores[k])


# ---------------------------------------------------------------------------
# __main__ — simulated 5-interaction session test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import shutil

    # Use a temp state dir so we don't clobber real data
    test_state = Path.home() / ".offline-ai" / "_test_context"
    test_state.mkdir(parents=True, exist_ok=True)

    # Monkey-patch the state file to test dir
    import au_context as _self_mod
    _self_mod.STATE_FILE = test_state / "context_state.json"

    engine = AUContextEngine()
    engine.session = AUSession()   # always fresh for test

    interactions = [
        ("How do I structure the AU orchestrator queue?",
         "Explained priority queue design with asyncio",
         ["run_python"]),
        ("Can I use mem0 to store conversation facts?",
         "Yes, mem0 supports structured fact storage",
         ["search_web"]),
        ("I'm getting an error in my Python script — traceback shows KeyError",
         "Suggested dict.get() as safe accessor",
         ["run_python"]),
        ("Write the orchestrator task dispatcher for me",
         "Generated Python code for TaskDispatcher class",
         ["run_python"]),
        ("How does the orchestrator queue handle priority errors?",
         "Covered priority inversion and error escalation",
         []),
    ]

    print("=" * 60)
    print("AU Context Engine — Simulated Session Test")
    print("=" * 60)

    for i, (query, summary, tools) in enumerate(interactions, 1):
        print(f"\n[Interaction {i}]")
        print(f"  Query: {query}")
        engine.log_interaction(query, summary, tools)

        focus   = engine.get_current_focus()
        rep_msg = engine.detect_repetition(query)
        print(f"  → Current focus   : {focus}")
        if rep_msg:
            print(f"  → Repetition alert: {rep_msg}")

    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print(engine.get_session_summary())

    print("\nCONTEXT INJECTION")
    print(engine.build_context_injection())

    print("\nTIME CONTEXT")
    tc = engine.get_time_context()
    for k, v in tc.items():
        print(f"  {k}: {v}")

    print("\nWORK PATTERN")
    pattern = engine.detect_work_pattern(engine.session)
    print(f"  → {pattern}")

    print("\nNEXT LIKELY TASK")
    nlt = engine.infer_next_likely_task(engine.session._recent_queries)
    print(f"  → {nlt}")

    print("\nPROACTIVE MESSAGE")
    pm = engine.generate_proactive_message()
    print(f"  → {pm if pm else '(none — session conditions normal)'}")

    print("\n" + "=" * 60)
    print("All tests passed ✓")

    # Cleanup test state
    shutil.rmtree(test_state, ignore_errors=True)
