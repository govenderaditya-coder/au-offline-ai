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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-record")
SPEAK_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-speak")
ACTIONS_MODULE = os.path.join(SCRIPT_DIR, "src", "app")
sys.path.insert(0, ACTIONS_MODULE)

import au_actions
import au_voice_id

# Initialize Faster-Whisper locally
from faster_whisper import WhisperModel

print("[AU_STATE:INITIALIZING]", flush=True)
print("⚡ Loading local Whisper Neural Engine...", flush=True)
whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
print("[AU_STATE:READY]", flush=True)

MODEL_NAME = "au-assistant:latest"

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

    if os.path.exists(SPEAK_TOOL):
        subprocess.run([SPEAK_TOOL, cleaned])
    else:
        subprocess.run(["say", "-v", "Samantha", cleaned])

def query_au(user_prompt: str) -> str:
    """Queries local Ollama au-assistant model with document grounded instructions."""
    url = "http://localhost:11434/api/generate"
    payload = json.dumps({
        "model": MODEL_NAME,
        "prompt": user_prompt,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except Exception as e:
        return f"I had trouble connecting to my local brain: {e}"

def listen_and_transcribe() -> str:
    """Records voice when speech is detected and transcribes it locally."""
    if not os.path.exists(RECORD_TOOL):
        return ""
    try:
        emit_state("LISTENING")
        proc = subprocess.Popen([RECORD_TOOL], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check stderr for hearing state
        stdout, stderr = proc.communicate(timeout=18)
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
        return ""

def process_command(command: str):
    """Parses user intent, executes Mac actions, and speaks response."""
    cmd_lower = command.lower()

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

    emit_state("THINKING")
    print(f"🧠 [AU THINKING]: Analyzing request: \"{command}\"", flush=True)

    raw_response = query_au(command)

    emit_state("EXECUTING")
    speech_text, executed_actions = au_actions.parse_and_execute(raw_response)

    if executed_actions:
        for act in executed_actions:
            print(f"[AU_ACTION:{act}]", flush=True)
            print(f"⚡ [ACTION EXECUTED]: {act}", flush=True)

    speak(speech_text)
    return "continue"

def main():
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
            speak("Goodbye!")
            break

if __name__ == "__main__":
    main()
