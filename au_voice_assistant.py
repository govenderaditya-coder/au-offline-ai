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

# Initialize Central Orchestrator Core
orchestrator = au_orchestrator.AUOrchestrator()

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

def process_command(command: str):
    """
    Parses user intent, executes Mac actions via OpenHands Action/Observation loop,
    and speaks response with Mem0 personal context grounding.
    """
    cmd_lower = command.lower().strip()

    if "go to sleep" in cmd_lower or "stop listening" in cmd_lower:
        speak("Going to standby. Say 'Wake up AU' when you need me.")
        return "sleep"

    if "turn on voice lock" in cmd_lower:
        au_voice_id.set_voice_lock(True)
        speak("Voice Lock enabled. I will now prioritize commands from Aditya.")
        return "continue"

    if "turn off voice lock" in cmd_lower:
        au_voice_id.set_voice_lock(False)
        speak("Voice Lock disabled. Accepting all voice inputs.")
        return "continue"

    # Direct memory commands
    if any(q in cmd_lower for q in ["what do you remember", "what are my memories", "show my memories", "check memory"]):
        memories = memory_engine.list_all(limit=5)
        if not memories:
            speak("I do not have any personal memories stored yet.")
        else:
            summary = "Here is what I remember: " + "; ".join([m["fact"] for m in memories[:3]])
            speak(summary)
        return "continue"

    if "forget everything" in cmd_lower or "clear my memory" in cmd_lower:
        memory_engine.clear_all()
        speak("I have cleared all stored personal memories.")
        return "continue"

    # Fast background fact extraction
    try:
        learned = au_memory.extract_and_store_facts(command, memory_engine)
        if learned:
            print(f"🧠 [MEM0 LEARNED]: {learned}", flush=True)
    except Exception:
        pass

    # Determine target domain layer
    active_model, persona_name, persona_desc = get_active_model_and_persona()
    if persona_name == "coder" or any(k in cmd_lower for k in ["code", "syntax", "git commit", "diff", "edit file", "repo"]):
        layer = "coding"
        cost = au_orchestrator.MemoryCost.MEDIUM
    elif persona_name == "researcher" or any(k in cmd_lower for k in ["document", "pdf", "summarize notes", "research paper"]):
        layer = "document_search"
        cost = au_orchestrator.MemoryCost.MEDIUM
    elif any(k in cmd_lower for k in ["volume", "battery", "open app", "close app", "screenshot", "disk", "time"]):
        layer = "chat"
        cost = au_orchestrator.MemoryCost.LOW
    else:
        layer = "chat"
        cost = au_orchestrator.MemoryCost.LOW

    emit_state("THINKING")
    print(f"🧠 [AU ORCHESTRATOR ({layer.upper()})]: Dispatching \"{command}\"", flush=True)

    task = au_orchestrator.AUTask(
        layer=layer,
        prompt=command,
        payload={"is_voice": True},
        priority=au_orchestrator.TaskPriority.URGENT,
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

    speak(final_speech)
    return "continue"
    return "continue"

def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    emit_state("READY")
    speak("Hello Aditya! AU is online. Speak your command anytime.")

    is_sleeping = False

    while True:
        try:
            if is_sleeping:
                emit_state("STANDBY")
                heard = listen_and_transcribe()
                if heard and ("wake up" in heard.lower() or "hey au" in heard.lower() or "au" in heard.lower()):
                    is_sleeping = False
                    speak("I am back awake and ready.")
                time.sleep(0.2)
                continue

            user_speech = listen_and_transcribe()

            if not user_speech or len(user_speech) < 2:
                time.sleep(0.1)
                continue

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
