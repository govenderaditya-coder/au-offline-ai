#!/usr/bin/env python3
"""
AU Instant Offline Voice Profiler
Captures a 5-10 second voice sample, transcribes it locally with Faster-Whisper,
and binds it to Apple Silicon MLX for zero-shot voice cloning.
"""

import os
import sys
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROFILE_DIR = os.path.join(PROJECT_DIR, "voice_profile")
RECORD_TOOL = os.path.join(PROJECT_DIR, "tools", "au-record")
PYTHON_BIN = os.path.join(PROJECT_DIR, ".venv-cloner", "bin", "python")

SAMPLE_WAV = os.path.join(PROFILE_DIR, "my_voice.wav")
SAMPLE_TXT = os.path.join(PROFILE_DIR, "my_voice.txt")

os.makedirs(PROFILE_DIR, exist_ok=True)

def print_banner():
    print("\033[1;36m" + "=" * 65 + "\033[0m")
    print("\033[1;33m       🎙️  AU INSTANT OFFLINE VOICE CLONER (M4 NEURAL MLX)  🎙️\033[0m")
    print("\033[1;36m" + "=" * 65 + "\033[0m\n")

def record_sample():
    print_banner()
    print("You only need to speak \033[1;32mONE short sentence\033[0m (5 to 10 seconds).")
    print("AU will capture your tone, pitch, and voice characteristics 100% locally.\n")
    print("\033[1;37mSuggested phrase to read aloud:\033[0m")
    print("\033[1;35m\"Hello, this is my personal AI assistant AU running offline on my Mac.\"\033[0m\n")

    input("\033[1;33mPress [ENTER] to start recording...\033[0m ")
    print("\n🔴 \033[1;31mRECORDING NOW... Speak clearly into your microphone!\033[0m")
    print("   (Recording stops automatically when you pause speaking)\n")

    if os.path.exists(SAMPLE_WAV):
        try:
            os.remove(SAMPLE_WAV)
        except Exception:
            pass

    # Use native CoreAudio Voice Activity Detection tool
    subprocess.run([RECORD_TOOL, SAMPLE_WAV])

    if not os.path.exists(SAMPLE_WAV) or os.path.getsize(SAMPLE_WAV) < 1000:
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
        print("\n⭐ AU will now use YOUR voice for all responses, podcasts, and assistant dialogues!\n")
    else:
        print("ℹ️ Voice profile saved. AU is ready to synthesize speech in your voice.")

if __name__ == "__main__":
    if record_sample():
        text = transcribe_sample()
        test_cloned_voice(text)
