#!/usr/bin/env python3
"""
AU Voice Assistant — Personal Assistant for macOS
Listens to your voice commands, executes actions on your Mac, and speaks back!
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIONS_MODULE = os.path.join(SCRIPT_DIR, "src", "app", "au_actions.py")
LISTEN_TOOL = os.path.join(SCRIPT_DIR, "tools", "au-listen")

# Import actions module
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src", "app"))
import au_actions

VOICE_NAME = "Samantha"  # or Daniel, Karen
MODEL_NAME = "au-assistant:latest"

def speak(text: str):
    """Speaks text using macOS native speech synthesis."""
    if not text:
        return
    # Clean text of markdown, quotes, brackets
    cleaned = text.replace("*", "").replace("#", "").replace("[", "").replace("]", "").strip()
    if not cleaned:
        return
    subprocess.Popen(["say", "-v", VOICE_NAME, cleaned])

def query_au(user_prompt: str) -> str:
    """Sends prompt to local Ollama au-assistant model."""
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
        return f"Sorry, I had trouble reaching my brain: {e}"

def listen_voice() -> str:
    """Uses au-listen native binary to capture speech."""
    if not os.path.exists(LISTEN_TOOL):
        return ""
    try:
        res = subprocess.run([LISTEN_TOOL], capture_output=True, text=True, timeout=18)
        return res.stdout.strip()
    except Exception:
        return ""

def process_command(command: str):
    """Processes a user command, executes actions, and speaks back."""
    if not command:
        return
    
    print(f"\n👤 You said: \033[1;36m\"{command}\"\033[0m")
    print("🧠 AU is thinking...")
    
    raw_response = query_au(command)
    speech_text, executed_actions = au_actions.parse_and_execute(raw_response)
    
    if executed_actions:
        print("⚡ \033[1;32mActions executed:\033[0m")
        for act in executed_actions:
            print(f"   • {act}")
            
    print(f"🤖 \033[1;33mAU:\033[0m {speech_text}\n")
    speak(speech_text)

def main():
    print("""
╔══════════════════════════════════════════════════╗
║        🤖 AU — Personal Voice Assistant          ║
║      Voice-Controlled Mac Automation Agent       ║
╚══════════════════════════════════════════════════╝
    """)
    print("Voice Engine:  \033[1;32mApple Native Speech Framework\033[0m")
    print("Brain Engine:  \033[1;32mOllama + au-assistant (Llama 3.1 8B)\033[0m")
    print("Speech Output: \033[1;32m" + VOICE_NAME + " (macOS High-Res)\033[0m")
    print("-" * 52)
    print("Press \033[1;33m[V]\033[0m + Enter to speak with your microphone")
    print("Or simply \033[1;33mtype your command\033[0m and press Enter")
    print("Type \033[1;31mquit\033[0m to exit\n")

    speak("AU Personal Assistant is online and ready for your commands.")

    while True:
        try:
            user_input = input("\033[1;34mCommand [V for voice] > \033[0m").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                speak("Goodbye!")
                break
            
            if user_input.lower() == "v":
                print("🎙️ Listening... (Speak your command now into the microphone)")
                spoken = listen_voice()
                if not spoken:
                    print("⚠️ Didn't catch that. Try speaking louder or typing.")
                    continue
                process_command(spoken)
            else:
                process_command(user_input)

        except KeyboardInterrupt:
            print("\nExiting AU...")
            break

if __name__ == "__main__":
    main()
