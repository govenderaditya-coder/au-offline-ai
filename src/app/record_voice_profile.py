#!/usr/bin/env python3
"""
AU Voice Cloning Studio — Separate & Isolated Module
Captures a 5-10 second voice sample, transcribes it locally with Faster-Whisper,
and binds it to Apple Silicon MLX for zero-shot voice cloning.
"""

import os
import sys
import json
import time
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROFILE_DIR = os.path.join(PROJECT_DIR, "voice_profile")
RECORD_TOOL = os.path.join(PROJECT_DIR, "tools", "au-record")
PYTHON_BIN = os.path.join(PROJECT_DIR, ".venv-cloner", "bin", "python")
CONFIG_FILE = os.path.expanduser("~/.offline-ai/voice_config.json")

SAMPLE_WAV = os.path.join(PROFILE_DIR, "my_voice.wav")
SAMPLE_TXT = os.path.join(PROFILE_DIR, "my_voice.txt")

os.makedirs(PROFILE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

def print_banner():
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    print("\033[1;33m       🎙️  AU VOICE CLONING STUDIO (ISOLATED SEGMENT)  🎙️\033[0m")
    print("\033[1;36m" + "=" * 65 + "\033[0m\n")

def record_sample():
    print_banner()
    print("Record a short voice sample (5 to 10 seconds).")
    print("Suggested sentence to speak:")
    print("\033[1;35m\"Hello, this is my personal AI assistant AU running offline on my Mac.\"\033[0m\n")

    if "--auto" not in sys.argv:
        try:
            input("\033[1;33mPress [ENTER] to start recording...\033[0m ")
        except (EOFError, KeyboardInterrupt):
            pass

    for i in range(3, 0, -1):
        print(f"⏳ Starting in {i}...", end="\r", flush=True)
        time.sleep(0.7)

    print("\n🔴 \033[1;31mRECORDING NOW... Speak into your microphone!\033[0m")
    print("   (Recording stops automatically when you pause speaking)\n")

    if os.path.exists(SAMPLE_WAV):
        try:
            os.remove(SAMPLE_WAV)
        except Exception:
            pass

    # Explicitly pass target output path to au-record
    subprocess.run([RECORD_TOOL, SAMPLE_WAV])

    if not os.path.exists(SAMPLE_WAV) or os.path.getsize(SAMPLE_WAV) < 5000:
        print("❌ Recording failed or was too short. Please try again.")
        return False

    print("✅ \033[1;32mRecording captured successfully!\033[0m")
    return True

def transcribe_sample():
    print("\n⚡ \033[1;34m[ANALYZING]\033[0m Transcribing your speech locally with Whisper...")
    from faster_whisper import WhisperModel

    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(SAMPLE_WAV, beam_size=5)
    transcript = " ".join([seg.text for seg in segments]).strip()

    if not transcript:
        transcript = "Hello, this is my personal AI assistant AU running offline on my Mac."

    with open(SAMPLE_TXT, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"📝 \033[1;37mTranscribed Voice Sample:\033[0m \"{transcript}\"")
    print(f"💾 Voice profile saved to: \033[1;34m{SAMPLE_WAV}\033[0m")
    return transcript

def test_cloned_voice(transcript):
    print("\n🧠 \033[1;35m[MLX NEURAL CLONING]\033[0m Generating test greeting in YOUR cloned voice...")
    test_out = os.path.join(PROFILE_DIR, "test_greeting.wav")

    cmd = [
        PYTHON_BIN, "-m", "f5_tts_mlx.generate",
        "--text", "Hello Aditya! Your voice clone is ready. I am now speaking in your voice.",
        "--ref-audio", SAMPLE_WAV,
        "--ref-text", transcript,
        "--steps", "16",
        "--q", "8",
        "--output", test_out
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(test_out):
        print("\n🎉 \033[1;32m[VOICE CLONE ACTIVATED!]\033[0m Playing your cloned greeting now...")
        subprocess.run(["afplay", test_out])

        # Save config so AU knows cloned voice is available
        config = {"voice_gender": "cloned", "male_voice": "Daniel", "female_voice": "Samantha"}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

        print("\n⭐ Your cloned voice is saved in the Voice Studio segment and ready whenever you choose 'Cloned Voice'!\n")
    else:
        print("ℹ️ Voice profile recorded. AU can use this voice when enabled.")

if __name__ == "__main__":
    if record_sample():
        text = transcribe_sample()
        test_cloned_voice(text)
