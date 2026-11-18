#!/usr/bin/env python3
"""
AU Voice Assistant — Real-Time Hands-Free Agent
Communicates directly with native AU GUI via structured event stream:
  [AU_STATE:LISTENING]   - Waiting for user voice (your turn to speak)
  [AU_STATE:HEARING]     - Audio detected / recording speech
  [AU_STATE:THINKING]    - Running Ollama M4 Neural Brain
  [AU_STATE:EXECUTING]   - Automating Mac actions
  [AU_STATE:SPEAKING]    - Speaking voice response
  [AU_USER_TEXT: ...]    - Transcribed user speech
  [AU_RESPONSE_TEXT: ...]- AI answer text
"""

import os
import sys
import json
import time
import urllib.request
import subprocess
import signal
import re
import random
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-record")
SPEAK_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-speak")
ACTIONS_MODULE = os.path.join(SCRIPT_DIR, "src", "app")
sys.path.insert(0, ACTIONS_MODULE)

import au_actions
import au_tools
import au_memory
import au_voice_id
import au_orchestrator

# Optional emotion/personality engines (graceful fallback)
try:
    import au_emotion
    _emotion_engine = au_emotion.AUEmotionEngine()
except Exception:
    au_emotion = None
    _emotion_engine = None

# Initialize Central Orchestrator Core
orchestrator = au_orchestrator.AUOrchestrator()

# ── Session conversation memory (max 10 turns) ───────────────────────────────
session_history: list[tuple[str, str]] = []  # [(user_text, au_response), ...]

# ── Silence detection counter ─────────────────────────────────────────────────
silence_count: int = 0

# ── Wake-word variants ────────────────────────────────────────────────────────
_WAKE_PATTERNS = [
    r"\bhey\s+au\b",
    r"\bau\s+wake\s+up\b",
    r"\bwake\s+up\s+au\b",
    r"\byo\s+au\b",
    r"^au[,!.]?\s*$",         # bare "AU" (whole utterance)
    r"\bhey\s+assistant\b",
    r"\bau\b",                # any mention of "au" as a word
]

def is_addressed(text: str) -> bool:
    """Return True if any wake-word variant is detected in text."""
    t = text.lower().strip()
    for pat in _WAKE_PATTERNS:
        if re.search(pat, t):
            return True
    return False

# ── Intent classifier ─────────────────────────────────────────────────────────
_INTENT_RULES = [
    # (intent, layer, keyword_patterns, urgency_boost)
    ("code_request",    "coding",          [r"\b(code|function|class|script|bug|fix|debug|syntax|git|diff|refactor|implement)\b"], 0.0),
    ("file_operation",  "chat",            [r"\b(file|folder|directory|open|save|delete|move|copy|rename|read)\b"], 0.0),
    ("web_search",      "chat",            [r"\b(search|google|look up|find online|browse|web|internet)\b"], 0.0),
    ("system_control",  "chat",            [r"\b(volume|brightness|battery|screenshot|app|launch|quit|close|sleep|restart)\b"], 0.0),
    ("memory_query",    "chat",            [r"\b(remember|memory|memories|recall|forget|stored|know about me)\b"], 0.0),
    ("document_search", "document_search", [r"\b(document|pdf|notes|research|paper|summarize|article)\b"], 0.0),
    ("question",        "chat",            [r"^(what|who|where|when|why|how|is|are|does|do|can|could|would|should|tell me)\b"], 0.0),
    ("command",         "chat",            [r"^(open|close|set|turn|play|pause|stop|start|run|show|hide|switch)\b"], 0.1),
]

def classify_voice_intent(text: str) -> dict:
    """Classify spoken text into a structured intent dict."""
    t = text.lower().strip()
    entities: list[str] = []

    # Extract simple entities: quoted strings, app names, file extensions
    entities += re.findall(r'"([^"]+)"', t)
    entities += re.findall(r'\b[\w-]+\.(?:py|js|ts|md|txt|pdf|json|sh)\b', t)

    for intent, layer, patterns, urgency_boost in _INTENT_RULES:
        for pat in patterns:
            if re.search(pat, t):
                urgency = 0.5 + urgency_boost
                if any(w in t for w in ["urgent", "asap", "now", "immediately", "hurry"]):
                    urgency = min(1.0, urgency + 0.3)
                return {"intent": intent, "layer": layer, "urgency": urgency, "entities": entities}

    return {"intent": "conversation", "layer": "chat", "urgency": 0.3, "entities": entities}

# ── Emotional voice prefixes ───────────────────────────────────────────────────
_EMOTION_PREFIXES: dict[str, list[str]] = {
    "stressed":   ["I hear you — let me sort this out fast.", "On it, no worries."],
    "frustrated": ["I get it, that's annoying. Let me fix it.", "Understood — let's tackle this together."],
    "excited":    ["Yes! Let's do it.", "Love the energy — here we go!"],
    "happy":      ["Great! Here's what I found.", "Wonderful — let me help."],
    "curious":    ["Good question — let me think...", "Interesting! Here's my take."],
    "tired":      ["Sure, I'll keep it brief.", "No problem — quick answer coming."],
    "urgent":     ["Right away.", "On it immediately."],
    "calm":       ["Sure.", "Of course."],
}

def get_emotional_voice_prefix(detected_emotion: str) -> str:
    """Return an empathetic spoken opener based on detected user emotion."""
    options = _EMOTION_PREFIXES.get(detected_emotion.lower(), [])
    return random.choice(options) if options else ""

# ── Quick-response table (bypasses neural model entirely) ─────────────────────
def _quick_time() -> str:
    return datetime.now().strftime("It is %I:%M %p.")

def _quick_battery() -> str:
    try:
        res = au_tools.run_get_battery()
        if res and res.message:
            return res.message
    except Exception:
        pass
    try:
        out = subprocess.check_output(["pmset", "-g", "batt"], text=True)
        m = re.search(r"(\d+)%", out)
        if m:
            return f"Battery is at {m.group(1)} percent."
    except Exception:
        pass
    return "Battery info is currently unavailable."

def _quick_volume(direction: str) -> str:
    try:
        vol = 80 if direction == "up" else 30
        res = au_tools.run_set_volume(au_tools.SetVolumeArgs(volume=vol))
        if res and res.message:
            return res.message
        return f"Volume set {'up' if direction == 'up' else 'down'}."
    except Exception:
        try:
            delta = "+ 10" if direction == "up" else "- 10"
            cmd = f"set volume output volume (output volume of (get volume settings) {delta})"
            subprocess.call(["osascript", "-e", cmd])
            return f"Volume turned {direction}."
        except Exception:
            return "Volume adjusted."

def _quick_media(action: str) -> str:
    try:
        res = au_tools.run_media_control(au_tools.MediaControlArgs(command=action))
        if res and res.message:
            return res.message
        return f"{'Playing' if action == 'play' else 'Paused'} music."
    except Exception:
        try:
            key = "play" if action == "play" else "pause"
            subprocess.call(["osascript", "-e", f'tell application "Spotify" to {key}'])
            return f"{'Playing' if action == 'play' else 'Paused'} music."
        except Exception:
            return "Media playback updated."

QUICK_RESPONSES: dict[str, callable] = {
    r"\bwhat(?:'s| is) the time\b|\bwhat time is it\b": _quick_time,
    r"\bwhat(?:'s| is) (?:my )?battery\b":               _quick_battery,
    r"\bvolume up\b":                                     lambda: _quick_volume("up"),
    r"\bvolume down\b":                                   lambda: _quick_volume("down"),
    r"\bplay music\b":                                    lambda: _quick_media("play"),
    r"\bpause music\b":                                   lambda: _quick_media("pause"),
}

def try_quick_response(text: str) -> str | None:
    """Return a quick spoken response if text matches a fast-path pattern, else None."""
    t = text.lower().strip()
    for pat, fn in QUICK_RESPONSES.items():
        if re.search(pat, t):
            return fn()
    return None

# ── Session history helpers ───────────────────────────────────────────────────
def _add_to_history(user_text: str, au_response: str):
    global session_history
    session_history.append((user_text, au_response))
    if len(session_history) > 10:
        session_history = session_history[-10:]

def _build_history_messages(persona_desc: str) -> list[dict]:
    """Build Ollama message list from session history + current persona."""
    msgs = [{"role": "system", "content": persona_desc}]
    for u, a in session_history:
        msgs.append({"role": "user",      "content": u})
        msgs.append({"role": "assistant", "content": a})
    return msgs

# Initialize Faster-Whisper locally
from faster_whisper import WhisperModel

print("[AU_STATE:INITIALIZING]", flush=True)
print("⚡ Loading local Whisper Neural Engine...", flush=True)
whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

# Initialize Mem0 Long-Term Memory Engine
print("🧠 Initializing Mem0 Offline Memory Engine...", flush=True)
memory_engine = au_memory.AUMemoryEngine()
print("[AU_STATE:READY]", flush=True)

MODEL_NAME = "au-assistant:latest"
active_child = None
stopping = False

def get_active_model_and_persona() -> tuple[str, str, str]:
    """Reads user-selected persona from ~/.offline-ai/persona_config.json."""
    cfg_path = os.path.expanduser("~/.offline-ai/persona_config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                persona = data.get("active_persona", "automator").lower()
                if persona == "researcher":
                    return "au-notebooklm:latest", "researcher", "You are AU in Research Partner mode. Ground answers thoroughly in facts and documents."
                elif persona == "podcast":
                    return "au-notebooklm:latest", "podcast", "You are AU in Podcast Studio mode. Formulate spoken responses with natural conversational audio cadence."
                elif persona == "coder":
                    repo_map = ""
                    try:
                        from au_repo_map import get_compact_repo_map
                        repo_map = "\n" + get_compact_repo_map(".")
                    except Exception:
                        pass
                    desc = (
                        "You are AU in Code Architect mode. You specialize in terminal execution, bash tools, script editing, and precision diffs.\n"
                        "When editing code files, prefer: [ACTION: edit_file_patch(\"path\", \"search_block\", \"replace_block\")].\n"
                        "To verify syntax: [ACTION: verify_syntax(\"path\")].\n"
                        "To commit changes: [ACTION: git_auto_commit(\"message\")].\n"
                        + repo_map
                    )
                    return "au-assistant:latest", "coder", desc
                else:
                    return "au-assistant:latest", "automator", "You are AU in Mac Automator mode. Prioritize system actions: volume, Spotify, apps, screenshots, and Mac controls."
        except Exception:
            pass
    return "au-assistant:latest", "automator", "You are AU, the user's personal, highly intelligent AI assistant controlling their Mac."

def emit_state(state: str):
    """Emits state event to stdout for AU.app native GUI to render."""
    print(f"[AU_STATE:{state}]", flush=True)

def speak(text: str):
    """Speaks text using AU modular voice dispatcher (Male, Female, or Cloned)."""
    if not text:
        return
    cleaned = text.replace("*", "").replace("#", "").replace("[", "").replace("]", "").strip()
    if not cleaned:
        return

    emit_state("SPEAKING")
    print(f"[AU_RESPONSE_TEXT:{cleaned}]", flush=True)
    print(f"🗣️ [AU SPEAKING]: {cleaned}", flush=True)

    global active_child
    command = [SPEAK_TOOL, cleaned] if os.path.exists(SPEAK_TOOL) else ["say", "-v", "Samantha", cleaned]
    # Do not let a synthesizer or clone keep AU alive after the user presses Stop.
    active_child = subprocess.Popen(command, start_new_session=True)
    try:
        active_child.wait()
    finally:
        active_child = None

def query_au_chat(messages: list, model: str = None, timeout: int = 35) -> str:
    """Queries local Ollama model with multi-turn message history."""
    url = "http://localhost:11434/api/chat"
    target_model = model or MODEL_NAME
    payload = json.dumps({
        "model": target_model,
        "messages": messages,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"I had trouble connecting to my local brain: {e}"

def listen_and_transcribe() -> str:
    """Records voice when speech is detected and transcribes it locally."""
    if not os.path.exists(RECORD_TOOL):
        return ""
    try:
        emit_state("LISTENING")
        global active_child
        proc = subprocess.Popen([RECORD_TOOL], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        active_child = proc

        # Check stderr for hearing state
        stdout, stderr = proc.communicate(timeout=18)
        active_child = None
        if "[STATE:HEARING]" in stderr:
            emit_state("HEARING")

        if stdout.strip() == "AUDIO_READY":
            emit_state("THINKING")
            audio_path = "/tmp/au_speech.wav"
            if os.path.exists(audio_path):
                segments, info = whisper_model.transcribe(audio_path, beam_size=1)
                text = " ".join([s.text for s in segments]).strip()
                return text
        return ""
    except Exception:
        active_child = None
        return ""

def stop_active_child():
    global active_child
    if active_child and active_child.poll() is None:
        try:
            os.killpg(active_child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    active_child = None

def request_stop(_signum, _frame):
    """Make the GUI Stop button reliably stop recording, speech, and cloning."""
    global stopping
    stopping = True
    stop_active_child()
    emit_state("OFFLINE")
    raise KeyboardInterrupt

def generate_startup_greeting() -> str:
    """Generate an inspiring, mood- and time-aware opening greeting for AU startup."""
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

    time_str = now.strftime("%I:%M %p")
    mood = "calm"
    opening = f"Good {tod}, Aditya!"
    if _emotion_engine:
        try:
            mood = getattr(_emotion_engine._state, "current_mood", "calm")
            opening = _emotion_engine.generate_greeting(tod)
        except Exception:
            pass
    return f"{opening} It's {time_str}, and I'm feeling {mood}. Ready when you are."

def process_command(command: str):
    """
    Parses user intent, executes Mac actions via OpenHands Action/Observation loop,
    and speaks response with Mem0 personal context grounding and emotional intelligence.
    """
    cmd_lower = command.lower().strip()

    # 1. Quick responses (pure local, zero model latency)
    quick = try_quick_response(command)
    if quick:
        speak(quick)
        _add_to_history(command, quick)
        return "continue"

    # 2. Standby / sleep commands
    if "go to sleep" in cmd_lower or "stop listening" in cmd_lower:
        speak("Going to standby. Say 'Wake up AU' when you need me.")
        return "sleep"

    # 3. Voice lock commands
    if "turn on voice lock" in cmd_lower:
        au_voice_id.set_voice_lock(True)
        resp = "Voice Lock enabled. I will now prioritize commands from Aditya."
        speak(resp)
        _add_to_history(command, resp)
        return "continue"

    if "turn off voice lock" in cmd_lower:
        au_voice_id.set_voice_lock(False)
        resp = "Voice Lock disabled. Accepting all voice inputs."
        speak(resp)
        _add_to_history(command, resp)
        return "continue"

    # 4. Direct memory commands
    if any(q in cmd_lower for q in ["what do you remember", "what are my memories", "show my memories", "check memory"]):
        memories = memory_engine.list_all(limit=5)
        if not memories:
            resp = "I do not have any personal memories stored yet."
        else:
            resp = "Here is what I remember: " + "; ".join([m["fact"] for m in memories[:3]])
        speak(resp)
        _add_to_history(command, resp)
        return "continue"

    if "forget everything" in cmd_lower or "clear my memory" in cmd_lower:
        memory_engine.clear_all()
        resp = "I have cleared all stored personal memories."
        speak(resp)
        _add_to_history(command, resp)
        return "continue"

    # 5. Fast background fact extraction
    try:
        learned = au_memory.extract_and_store_facts(command, memory_engine)
        if learned:
            print(f"🧠 [MEM0 LEARNED]: {learned}", flush=True)
    except Exception:
        pass

    # 6. Smart intent classification & routing
    intent_data = classify_voice_intent(command)
    intent = intent_data["intent"]
    layer = intent_data["layer"]
    urgency_val = intent_data["urgency"]
    entities = intent_data["entities"]

    active_model, persona_name, persona_desc = get_active_model_and_persona()
    if persona_name == "coder":
        layer = "coding"
        cost = au_orchestrator.MemoryCost.MEDIUM
    elif persona_name == "researcher":
        layer = "document_search"
        cost = au_orchestrator.MemoryCost.MEDIUM
    elif layer in ["coding", "document_search"]:
        cost = au_orchestrator.MemoryCost.MEDIUM
    else:
        cost = au_orchestrator.MemoryCost.LOW

    # 7. Emotion analysis and adaptation
    detected_emotion = "calm"
    if _emotion_engine:
        try:
            emo_analysis = _emotion_engine.analyze_user_emotion(command)
            detected_emotion = emo_analysis.get("emotion", "calm")
            _emotion_engine.update_mood(emo_analysis, context="voice")
        except Exception:
            pass

    # 8. Build multi-turn conversational message history
    formatted_messages = []
    for u, a in session_history:
        formatted_messages.append({"role": "user", "content": u})
        formatted_messages.append({"role": "assistant", "content": a})
    formatted_messages.append({"role": "user", "content": command})

    priority = au_orchestrator.TaskPriority.URGENT if urgency_val >= 0.7 else au_orchestrator.TaskPriority.HIGH

    emit_state("THINKING")
    print(f"🧠 [AU ORCHESTRATOR ({layer.upper()})]: Intent={intent} | Dispatching \"{command}\"", flush=True)

    task = au_orchestrator.AUTask(
        layer=layer,
        prompt=command,
        payload={
            "is_voice": True,
            "messages": formatted_messages,
            "history": session_history,
            "session_history": session_history,
            "intent": intent,
            "entities": entities,
        },
        priority=priority,
        memory_cost=cost
    )
    orchestrator.queue.submit(task)
    completed_task = orchestrator.dispatch(task)

    if completed_task.status == au_orchestrator.TaskStatus.PAUSED:
        speak("Task paused: Memory is tight on Apple Silicon. I will resume when RAM clears.")
        return "continue"

    if completed_task.status == au_orchestrator.TaskStatus.FAILED:
        speak(f"I had trouble completing that task: {completed_task.error}")
        return "continue"

    res = completed_task.result or {}
    final_speech = res.get("text", "")
    actions = res.get("actions", [])

    if actions:
        emit_state("EXECUTING")
        for act in actions:
            print(f"[AU_ACTION:{act}]", flush=True)
            print(f"⚡ [ACTION EXECUTED]: {act}", flush=True)

    # 9. Apply emotional voice prefix
    prefix = get_emotional_voice_prefix(detected_emotion)
    if prefix and final_speech and not final_speech.startswith(prefix):
        final_speech = f"{prefix} {final_speech}"

    speak(final_speech)
    _add_to_history(command, final_speech)
    return "continue"

def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    emit_state("READY")

    # Startup greeting with time, mood, and inspiring opening
    greeting = generate_startup_greeting()
    speak(greeting)

    global silence_count
    is_sleeping = False

    while True:
        try:
            if is_sleeping:
                emit_state("STANDBY")
                heard = listen_and_transcribe()
                if heard and is_addressed(heard):
                    is_sleeping = False
                    silence_count = 0
                    speak("I am back awake and ready.")
                time.sleep(0.2)
                continue

            user_speech = listen_and_transcribe()

            if not user_speech or len(user_speech) < 2:
                silence_count += 1
                if silence_count == 3:
                    speak("I'm here — just speak when you're ready.")
                time.sleep(0.1)
                continue

            # Reset silence counter upon receiving valid speech
            silence_count = 0

            print(f"[AU_USER_TEXT:{user_speech}]", flush=True)
            print(f"👤 [YOU SAID]: \"{user_speech}\"", flush=True)

            status = process_command(user_speech)
            if status == "sleep":
                is_sleeping = True

        except KeyboardInterrupt:
            emit_state("OFFLINE")
            if not stopping:
                speak("Goodbye!")
            break

if __name__ == "__main__":
    main()
