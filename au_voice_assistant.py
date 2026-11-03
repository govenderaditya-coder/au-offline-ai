#!/usr/bin/env python3
"""
AU Voice Assistant — Hands-Free Interactive Personal Assistant
Continuously listens to your voice, executes Mac actions, and speaks back.
No keyboard needed.
"""

import os
import sys
import json
import time
import urllib.request
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_MODULE = os.path.join(SCRIPT_DIR, "src", "app", "au_actions.py")
LISTEN_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-listen")

sys.path.insert(0, os.path.join(SCRIPT_DIR, "src", "app"))
import au_actions
import au_voice_id

VOICE_NAME = "Samantha"  # macOS voice (Samantha, Daniel, etc.)
MODEL_NAME = "au-assistant:latest"

def speak(text: str):
    """Speaks text using macOS native speech synthesis (blocking so mic doesn't hear itself)."""
    if not text:
        return
    cleaned = text.replace("*", "").replace("#", "").replace("[", "").replace("]", "").strip()
    if not cleaned:
        return
    print(f"\n🗣️ \033[1;33m[AU SPEAKING]:\033[0m {cleaned}\n")
    # Blocking call ensures AU never listens to his own voice!
    subprocess.run(["say", "-v", VOICE_NAME, cleaned])

def query_au(user_prompt: str) -> str:
    """Queries the local Ollama au-assistant model."""
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

def listen_once() -> str:
    """Listens to microphone until silence using the native Apple Speech tool."""
    if not os.path.exists(LISTEN_TOOL):
        return ""
    try:
        res = subprocess.run([LISTEN_TOOL], capture_output=True, text=True, timeout=18)
        return res.stdout.strip()
    except Exception:
        return ""

def process_command(command: str):
    """Parses intent, runs Mac automation actions, and speaks back."""
    cmd_lower = command.lower()

    # Built-in Voice Assistant quick overrides
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

    print("🧠 \033[1;34m[AU THINKING]\033[0m Analyzing request and planning actions...")
    raw_response = query_au(command)
    speech_text, executed_actions = au_actions.parse_and_execute(raw_response)

    if executed_actions:
        print("⚡ \033[1;32m[ACTIONS EXECUTED ON MAC]:\033[0m")
        for act in executed_actions:
            print(f"   ✓ {act}")

    speak(speech_text)
    return "continue"

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║             🤖 AU — HANDS-FREE VOICE ASSISTANT               ║
║           Continuous Interactive Voice Control               ║
╚══════════════════════════════════════════════════════════════╝
    """)
    print("• Mode:         \033[1;32mHands-Free Interactive (No keyboard needed)\033[0m")
    print("• Speech Input: \033[1;32mApple Native Speech Framework (M4 Hardware Accel)\033[0m")
    print("• Speech Voice: \033[1;32m" + VOICE_NAME + " (macOS High-Res)\033[0m")
    print("• Voice Lock:   \033[1;32m" + ("Active (Aditya)" if au_voice_id.is_voice_lock_active() else "Ready to Train") + "\033[0m")
    print("-" * 64)
    print("👉 Simply start speaking. When you finish, AU responds automatically.")
    print("👉 Say \033[1;33m'Go to sleep'\033[0m to pause, or \033[1;31mCtrl+C\033[0m to quit.\n")

    speak("Hello Aditya! AU is listening. Speak your command anytime.")

    is_sleeping = False

    while True:
        try:
            if is_sleeping:
                print("💤 \033[1;30m[STANDBY] Sleeping... (Say 'Wake up AU' or press Enter)\033[0m")
                heard = listen_once()
                if heard and ("wake up" in heard.lower() or "hey au" in heard.lower() or "au" in heard.lower()):
                    is_sleeping = False
                    speak("I am back awake and ready.")
                continue

            print("🟢 \033[1;32m[LISTENING] Speak now...\033[0m", end="", flush=True)
            user_speech = listen_once()

            if not user_speech:
                # Brief pause before re-arming mic
                time.sleep(0.1)
                continue

            print(f"\r👤 \033[1;36m[YOU SAID]:\033[0m \"{user_speech}\"")

            status = process_command(user_speech)
            if status == "sleep":
                is_sleeping = True

        except KeyboardInterrupt:
            print("\n👋 Exiting AU Voice Assistant...")
            speak("Goodbye!")
            break

if __name__ == "__main__":
    main()
