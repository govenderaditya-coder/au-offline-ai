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
                    return "au-assistant:latest", "coder", "You are AU in Code Architect mode. Prioritize terminal execution, bash tools, script editing, and technical precision."
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

    # Retrieve relevant personal memory context
    memory_context = memory_engine.format_context_prompt(command)
    active_model, persona_name, persona_desc = get_active_model_and_persona()

    # Base system instructions with MCP tool capabilities
    system_prompt = (
        f"{persona_desc}\n"
        "You execute tasks on macOS using action tags or JSON tool calls.\n"
        "Available actions:\n"
        "- [ACTION: open_app(\"App Name\")]\n"
        "- [ACTION: close_app(\"App Name\")]\n"
        "- [ACTION: set_volume(percentage_0_to_100)]\n"
        "- [ACTION: media_control(\"play\"|\"pause\"|\"next\"|\"prev\")]\n"
        "- [ACTION: search_web(\"query\")]\n"
        "- [ACTION: open_url(\"https://...\")]\n"
        "- [ACTION: get_battery()]\n"
        "- [ACTION: get_disk_space()]\n"
        "- [ACTION: get_time()]\n"
        "- [ACTION: take_screenshot()]\n"
        "- [ACTION: create_note(\"Title\", \"Content\")]\n"
        "- [ACTION: open_folder(\"path\")]\n"
        "- [ACTION: read_file(\"path\")]\n"
        "- [ACTION: execute_bash(\"command\")]\n"
        "\nGUIDELINES:\n"
        "1. Emit action tags first when an action or information retrieval is required.\n"
        "2. Keep spoken responses concise, friendly, and natural (1-2 sentences) for voice.\n"
        "3. When you receive an Observation, use the factual observation to answer the user accurately.\n"
        + memory_context
    )

    emit_state("THINKING")
    print(f"🧠 [AU THINKING ({persona_name.upper()})]: Analyzing request: \"{command}\"", flush=True)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": command}
    ]

    max_steps = 5
    clean_speech = ""

    for step in range(max_steps):
        raw_response = query_au_chat(messages, model=active_model)

        # Parse actions and tool calls
        clean_text, executed_actions, tool_results = au_tools.parse_and_execute_all(raw_response)
        clean_speech = clean_text or clean_speech

        # If no actions were called, this is the final spoken response
        if not executed_actions:
            final_speech = clean_text or raw_response
            speak(final_speech)
            return "continue"

        # Actions were executed
        emit_state("EXECUTING")
        for act in executed_actions:
            print(f"[AU_ACTION:{act}]", flush=True)
            print(f"⚡ [ACTION EXECUTED]: {act}", flush=True)

        # Check if an observation is needed (information retrieval tool vs simple side-effect)
        has_info_retrieval = any(
            any(k in act.lower() for k in ["battery", "disk", "time", "read", "bash", "status", "free out of", "%", "screenshot saved", "created note"])
            for act in executed_actions
        )

        # If it was a simple side-effect and the assistant already spoke a complete sentence, finish immediately
        if not has_info_retrieval and clean_text and len(clean_text) > 12:
            speak(clean_text)
            return "continue"

        # Feed the Observation back into the OpenHands loop
        observation_str = "Observation: " + " | ".join(executed_actions)
        messages.append({"role": "assistant", "content": raw_response})
        messages.append({
            "role": "user",
            "content": f"{observation_str}\nNow provide a concise, natural spoken response for the user based on this observation."
        })

        emit_state("THINKING")

    # If loop concludes, speak last response
    if clean_speech:
        speak(clean_speech)
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
