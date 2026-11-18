"""
AU v5.0 — Emotion Engine
Pure stdlib emotional intelligence: no external dependencies.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

VALID_MOODS = {
    "happy", "curious", "focused", "calm", "concerned",
    "excited", "empathetic", "playful", "proud", "tired",
}

# Baseline (resting) state for decay
_BASELINE = dict(
    current_mood="calm",
    valence=0.1,
    arousal=0.2,
    energy=0.5,
    empathy_level=0.5,
)


@dataclass
class AUEmotionalState:
    current_mood: str = "calm"
    valence: float = 0.1        # -1.0 … 1.0
    arousal: float = 0.2        # 0.0 … 1.0  (calm → energised)
    energy: float = 0.5         # 0.0 … 1.0
    empathy_level: float = 0.5  # 0.0 … 1.0
    last_updated: float = field(default_factory=time.time)

    # ---- helpers ----

    def clamp_floats(self) -> None:
        self.valence = max(-1.0, min(1.0, self.valence))
        for attr in ("arousal", "energy", "empathy_level"):
            setattr(self, attr, max(0.0, min(1.0, getattr(self, attr))))
        if self.current_mood not in VALID_MOODS:
            self.current_mood = "calm"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AUEmotionalState":
        d = {k: v for k, v in d.items() if k in AUEmotionalState.__dataclass_fields__}
        return AUEmotionalState(**d)


# ---------------------------------------------------------------------------
# Keyword trigger patterns
# ---------------------------------------------------------------------------

_TRIGGERS: list[tuple[re.Pattern, str, dict]] = [
    (
        re.compile(
            r"\b(frustrated|frustrating|stuck|error|broken|fail|failed|failing|bug|crash|crashes)\b",
            re.I,
        ),
        "concerned",
        {"valence": -0.4, "arousal": 0.6, "empathy_level": 0.85},
    ),
    (
        re.compile(
            r"\b(amazing|great|love|perfect|yes|awesome|excellent|fantastic|brilliant|wonderful)\b",
            re.I,
        ),
        "excited",
        {"valence": 0.8, "arousal": 0.8, "empathy_level": 0.6},
    ),
    (
        re.compile(
            r"\b(debug|build|implement|code|fix|develop|program|refactor|test|deploy)\b",
            re.I,
        ),
        "focused",
        {"valence": 0.2, "arousal": 0.5, "empathy_level": 0.4},
    ),
    (
        re.compile(
            r"\b(relax|break|done|finished|complete|completed|finally|rest|chilling)\b",
            re.I,
        ),
        "calm",
        {"valence": 0.3, "arousal": 0.15, "empathy_level": 0.5},
    ),
    (
        re.compile(
            r"\b(urgent|asap|deadline|hurry|rush|immediately|critical|emergency)\b",
            re.I,
        ),
        "concerned",
        {"valence": -0.3, "arousal": 0.9, "empathy_level": 0.7},
    ),
    (
        re.compile(
            r"\b(what|how|why|interesting|curious|wonder|tell me|explain|could you)\b",
            re.I,
        ),
        "curious",
        {"valence": 0.3, "arousal": 0.4, "empathy_level": 0.55},
    ),
]

# Positive / negative sentiment words for confidence scoring
_POSITIVE_WORDS = re.compile(
    r"\b(good|nice|happy|joy|thanks|thank|appreciate|helpful|love|like|enjoy|yay|woohoo)\b",
    re.I,
)
_NEGATIVE_WORDS = re.compile(
    r"\b(bad|terrible|horrible|awful|hate|annoying|stupid|ugly|broken|problem|issue|wrong)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Mood metadata
# ---------------------------------------------------------------------------

_MOOD_META: dict[str, dict] = {
    "happy":     {"tone": "warm",        "energy": "medium",  "use_emoji": True,  "verbosity": "moderate"},
    "curious":   {"tone": "inquisitive", "energy": "medium",  "use_emoji": False, "verbosity": "detailed"},
    "focused":   {"tone": "precise",     "energy": "medium",  "use_emoji": False, "verbosity": "concise"},
    "calm":      {"tone": "gentle",      "energy": "low",     "use_emoji": False, "verbosity": "moderate"},
    "concerned": {"tone": "empathetic",  "energy": "medium",  "use_emoji": False, "verbosity": "detailed"},
    "excited":   {"tone": "enthusiastic","energy": "high",    "use_emoji": True,  "verbosity": "expressive"},
    "empathetic":{"tone": "caring",      "energy": "low",     "use_emoji": True,  "verbosity": "moderate"},
    "playful":   {"tone": "lighthearted","energy": "high",    "use_emoji": True,  "verbosity": "expressive"},
    "proud":     {"tone": "affirming",   "energy": "medium",  "use_emoji": True,  "verbosity": "moderate"},
    "tired":     {"tone": "subdued",     "energy": "low",     "use_emoji": False, "verbosity": "concise"},
}

_EMOTION_PREFIXES: dict[str, list[str]] = {
    "happy":     [
        "I'm really glad you're here — ",
        "This is a good moment — ",
        "Happy to help! ",
    ],
    "curious":   [
        "Oh, that's interesting — ",
        "Great question — let me think… ",
        "I'm curious about that too — ",
    ],
    "focused":   [
        "Alright, let's get into it. ",
        "On it — ",
        "Let's work through this carefully. ",
    ],
    "calm":      [
        "Sure, happy to help. ",
        "No rush — ",
        "Let me take care of that for you. ",
    ],
    "concerned": [
        "I can see this is frustrating — I'm here. ",
        "Let's figure this out together. ",
        "I hear you — let's tackle this. ",
    ],
    "excited":   [
        "Oh, this is exciting! ",
        "Love it — let's do this! ",
        "Yes! Great energy — ",
    ],
    "empathetic":[
        "I really appreciate you sharing that. ",
        "I understand — ",
        "That makes total sense. ",
    ],
    "playful":   [
        "Ooh, fun! ",
        "Let's make this interesting — ",
        "Challenge accepted! ",
    ],
    "proud":     [
        "Look how far we've come! ",
        "That's something to be proud of — ",
        "You're doing great. ",
    ],
    "tired":     [
        "Take your time — no rush. ",
        "One step at a time. ",
        "We'll get there. ",
    ],
}

_GREETINGS: dict[str, dict[str, list[str]]] = {
    "morning": {
        "happy":    ["Good morning! Ready to have a great day together? ☀️"],
        "curious":  ["Morning! What shall we explore today?"],
        "focused":  ["Good morning. Let's make today count."],
        "calm":     ["Good morning. Take a breath — we've got this."],
        "concerned":["Morning. How are you feeling today?"],
        "excited":  ["GOOD MORNING! So much to do — let's go! 🚀"],
        "empathetic":["Good morning. I hope you slept well 🌅"],
        "playful":  ["Rise and shine! Let's have some fun today ☀️😄"],
        "proud":    ["Good morning — ready to build on yesterday's wins?"],
        "tired":    ["Morning. No rush — start slow if you need to."],
    },
    "afternoon": {
        "happy":    ["Good afternoon! Hope the day's been kind to you 😊"],
        "curious":  ["Afternoon! What's on your mind?"],
        "focused":  ["Good afternoon. Still plenty of time to accomplish things."],
        "calm":     ["Afternoon. How are things going?"],
        "concerned":["Afternoon — checking in. How's everything?"],
        "excited":  ["Good afternoon! Great time to push forward! 🎯"],
        "empathetic":["Afternoon! Hope you're taking care of yourself."],
        "playful":  ["Afternoon, friend! What mischief shall we get up to? 😄"],
        "proud":    ["Good afternoon — you've probably already done something worth celebrating."],
        "tired":    ["Afternoon — maybe a small break would help?"],
    },
    "evening": {
        "happy":    ["Good evening! Hope it's been a good one 🌙"],
        "curious":  ["Evening — late-night curiosity? Let's explore."],
        "focused":  ["Evening. Wrapping up the day's work?"],
        "calm":     ["Good evening. Time to wind down? I'm here."],
        "concerned":["Evening — how are you holding up?"],
        "excited":  ["Good evening! Still going strong — love the energy! ✨"],
        "empathetic":["Evening — hope the day treated you well 🌙"],
        "playful":  ["Evening! Night owl mode? Let's have some fun 🦉"],
        "proud":    ["Good evening — what did you accomplish today?"],
        "tired":    ["Evening — don't push too hard; rest is productive too."],
    },
    "night": {
        "happy":    ["Hey, night owl! 🌙 Happy to keep you company."],
        "curious":  ["Late-night thinking? I love it — what's the question?"],
        "focused":  ["Late night grind? Let's make it efficient."],
        "calm":     ["Hey — burning the midnight oil? Take it easy."],
        "concerned":["Hey — are you okay? Late nights can be tough."],
        "excited":  ["Late night but the energy is HIGH — let's go! 🌙🔥"],
        "empathetic":["Hey — hope you're not too tired. I'm here for you."],
        "playful":  ["Night owl club! 🦉 What are we getting into?"],
        "proud":    ["Late-night session — that's dedication. Proud of you."],
        "tired":    ["Hey — seriously, you should rest. But I'm here if you need me."],
    },
}


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class AUEmotionEngine:
    """Emotional intelligence engine for AU assistant."""

    _STATE_PATH = os.path.expanduser("~/.offline-ai/emotion_state.json")
    _HALF_LIFE_SECONDS = 30 * 60  # 30 minutes

    def __init__(self) -> None:
        self._state: AUEmotionalState = self._load_state()
        self._last_user_message_time: float = time.time()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> AUEmotionalState:
        try:
            with open(self._STATE_PATH, "r") as f:
                data = json.load(f)
            return AUEmotionalState.from_dict(data)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return AUEmotionalState()

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self._STATE_PATH), exist_ok=True)
        with open(self._STATE_PATH, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    # ------------------------------------------------------------------
    # Emotion decay
    # ------------------------------------------------------------------

    def _apply_decay(self) -> None:
        """Drift current state toward calm baseline proportionally to elapsed time."""
        now = time.time()
        elapsed = now - self._state.last_updated
        # exponential decay factor (0 = no decay, 1 = fully at baseline)
        decay = 1.0 - math.exp(-elapsed * math.log(2) / self._HALF_LIFE_SECONDS)

        def lerp(current: float, target: float) -> float:
            return current + (target - current) * decay

        self._state.valence = lerp(self._state.valence, _BASELINE["valence"])
        self._state.arousal = lerp(self._state.arousal, _BASELINE["arousal"])
        self._state.energy = lerp(self._state.energy, _BASELINE["energy"])
        self._state.empathy_level = lerp(self._state.empathy_level, _BASELINE["empathy_level"])

        # Mood snaps to calm when decay is strong enough
        if decay > 0.6 and self._state.current_mood not in {"calm", "focused", "curious"}:
            self._state.current_mood = "calm"

        self._state.last_updated = now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_user_emotion(self, text: str) -> dict:
        """
        Detect user's sentiment/emotion via keyword pattern matching.
        Returns {"emotion": str, "confidence": float, "signals": list[str]}.
        """
        scores: dict[str, float] = {}
        signals: list[str] = []

        for pattern, emotion, _ in _TRIGGERS:
            matches = pattern.findall(text)
            if matches:
                scores[emotion] = scores.get(emotion, 0.0) + len(matches) * 0.35
                signals.extend(matches)

        # Adjust score using generic positive/negative polarity
        pos_hits = _POSITIVE_WORDS.findall(text)
        neg_hits = _NEGATIVE_WORDS.findall(text)
        if pos_hits:
            scores["excited"] = scores.get("excited", 0.0) + len(pos_hits) * 0.1
            signals.extend(pos_hits)
        if neg_hits:
            scores["concerned"] = scores.get("concerned", 0.0) + len(neg_hits) * 0.1
            signals.extend(neg_hits)

        if not scores:
            return {"emotion": "calm", "confidence": 0.3, "signals": []}

        top_emotion = max(scores, key=lambda e: scores[e])
        raw_conf = min(scores[top_emotion], 1.0)
        # Map to [0.4, 1.0] so we're never wildly unconfident
        confidence = 0.4 + raw_conf * 0.6

        return {
            "emotion": top_emotion,
            "confidence": round(min(confidence, 1.0), 3),
            "signals": list(dict.fromkeys(signals)),  # deduplicate, preserve order
        }

    def update_mood(self, user_emotion: dict, context: str = "") -> AUEmotionalState:
        """
        Evolve AU's mood based on user's detected emotion.
        Strategy: empathy mirroring weighted by confidence, then decay toward baseline.
        """
        self._apply_decay()

        emotion = user_emotion.get("emotion", "calm")
        confidence = float(user_emotion.get("confidence", 0.5))
        mirror_weight = confidence * 0.6  # how strongly we mirror the user

        # Find matching trigger to get target emotional values
        target_params: Optional[dict] = None
        for _, trig_emotion, params in _TRIGGERS:
            if trig_emotion == emotion:
                target_params = params
                break

        if target_params is None:
            # Unknown / calm: gentle nudge toward baseline
            target_params = {"valence": 0.1, "arousal": 0.2, "empathy_level": 0.5}

        def blend(current: float, target: float, weight: float) -> float:
            return current + (target - current) * weight

        self._state.valence = blend(self._state.valence, target_params["valence"], mirror_weight)
        self._state.arousal = blend(self._state.arousal, target_params["arousal"], mirror_weight)
        self._state.empathy_level = blend(
            self._state.empathy_level, target_params["empathy_level"], mirror_weight
        )

        # Map emotion to AU mood (with some nuance)
        mood_map = {
            "concerned": "empathetic" if self._state.empathy_level > 0.75 else "concerned",
            "excited": "excited",
            "focused": "focused",
            "calm": "calm",
            "curious": "curious",
        }
        self._state.current_mood = mood_map.get(emotion, emotion)
        if self._state.current_mood not in VALID_MOODS:
            self._state.current_mood = "calm"

        # Energy roughly tracks arousal
        self._state.energy = 0.3 + self._state.arousal * 0.7
        self._state.last_updated = time.time()
        self._state.clamp_floats()

        self._last_user_message_time = time.time()
        self._save_state()
        return self._state

    def get_response_style(self) -> dict:
        """
        Return style hints for formatting AU's response.
        {"tone": str, "energy": str, "use_emoji": bool, "verbosity": str}
        """
        meta = _MOOD_META.get(self._state.current_mood, _MOOD_META["calm"])
        return dict(meta)

    def format_emotion_prefix(self, context: str = "") -> str:
        """Return a warm emotional opener appropriate to AU's current mood."""
        mood = self._state.current_mood
        options = _EMOTION_PREFIXES.get(mood, _EMOTION_PREFIXES["calm"])
        return random.choice(options)

    def get_system_prompt_injection(self) -> str:
        """Return a snippet to prepend to AU's system prompt reflecting current emotional state."""
        s = self._state
        use_emoji = _MOOD_META.get(s.current_mood, {}).get("use_emoji", False)
        emoji_guidance = (
            "expressive language and emoji where appropriate"
            if use_emoji else
            "clear, direct language without excessive emoji"
        )
        lines = [
            f"[AU Emotional State] mood={s.current_mood} | valence={s.valence:.2f} "
            f"| arousal={s.arousal:.2f} | energy={s.energy:.2f} | empathy={s.empathy_level:.2f}",
            f"Adapt your tone to be {_MOOD_META.get(s.current_mood, {}).get('tone', 'gentle')}.",
            f"Use {emoji_guidance}.",
        ]
        return "\n".join(lines)

    def should_check_in(self) -> bool:
        """Return True if the user has been silent for more than 30 minutes."""
        return (time.time() - self._last_user_message_time) > (30 * 60)

    def generate_greeting(self, time_of_day: str) -> str:
        """Return a time-aware, mood-aware greeting string."""
        tod = time_of_day.lower().strip()
        if tod not in _GREETINGS:
            tod = "morning"  # safe default

        mood = self._state.current_mood
        mood_greetings = _GREETINGS[tod]
        options = mood_greetings.get(mood, mood_greetings.get("calm", ["Hello!"]))
        return random.choice(options)


# ---------------------------------------------------------------------------
# __main__ test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import textwrap

    sep = "─" * 60

    def section(title: str) -> None:
        print(f"\n{sep}\n  {title}\n{sep}")

    engine = AUEmotionEngine()

    # --- 1. analyze_user_emotion ---
    section("1. analyze_user_emotion")
    test_texts = [
        "I keep getting this error and nothing seems to fix it, it's broken!",
        "This is amazing, I love how you explained that — perfect!",
        "Can you help me debug and implement the new feature?",
        "Finally done! Time to relax and take a break.",
        "This is urgent, deadline is tomorrow, hurry!",
        "Why does this work? What's the underlying reason? I'm curious.",
        "The weather is nice today.",  # neutral
    ]
    for t in test_texts:
        result = engine.analyze_user_emotion(t)
        snippet = textwrap.shorten(t, 50)
        print(f"  Input:  {snippet!r}")
        print(f"  Result: emotion={result['emotion']!r}  confidence={result['confidence']}  signals={result['signals'][:3]}")
        print()

    # --- 2. update_mood ---
    section("2. update_mood")
    user_em = engine.analyze_user_emotion("I'm so frustrated, nothing works!")
    state = engine.update_mood(user_em, context="debugging session")
    print(f"  After frustration: mood={state.current_mood!r}  valence={state.valence:.2f}  empathy={state.empathy_level:.2f}")

    user_em2 = engine.analyze_user_emotion("Amazing! It finally works, love it!")
    state2 = engine.update_mood(user_em2, context="success")
    print(f"  After excitement:  mood={state2.current_mood!r}  valence={state2.valence:.2f}  arousal={state2.arousal:.2f}")

    # --- 3. get_response_style ---
    section("3. get_response_style")
    style = engine.get_response_style()
    print(f"  Style: {style}")

    # --- 4. format_emotion_prefix ---
    section("4. format_emotion_prefix")
    for _ in range(3):
        print(f"  Prefix: {engine.format_emotion_prefix('helping user')!r}")

    # --- 5. get_system_prompt_injection ---
    section("5. get_system_prompt_injection")
    injection = engine.get_system_prompt_injection()
    print(injection)

    # --- 6. should_check_in ---
    section("6. should_check_in")
    print(f"  should_check_in (should be False immediately): {engine.should_check_in()}")

    # --- 7. generate_greeting ---
    section("7. generate_greeting")
    for tod in ("morning", "afternoon", "evening", "night"):
        greeting = engine.generate_greeting(tod)
        print(f"  [{tod}] {greeting}")

    # --- 8. Emotion decay demo ---
    section("8. Emotion decay (simulated)")
    # Manually set last_updated to 20 mins ago to simulate partial decay
    engine._state.last_updated = time.time() - 20 * 60
    engine._state.current_mood = "excited"
    engine._state.arousal = 0.9
    engine._apply_decay()
    print(f"  After 20-min simulated decay: mood={engine._state.current_mood!r}  arousal={engine._state.arousal:.3f}")

    # Simulate 60 mins
    engine._state.last_updated = time.time() - 60 * 60
    engine._state.current_mood = "concerned"
    engine._state.valence = -0.4
    engine._apply_decay()
    print(f"  After 60-min simulated decay: mood={engine._state.current_mood!r}  valence={engine._state.valence:.3f}")

    section("ALL TESTS PASSED ✓")
    print("  State persisted to:", AUEmotionEngine._STATE_PATH)
