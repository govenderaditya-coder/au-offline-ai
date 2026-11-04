#!/usr/bin/env python3
"""
AU MLX Speech Synthesizer
Uses Apple Silicon MLX GPU acceleration and F5-TTS to speak text in the cloned user voice.
"""

import os
import sys
import tempfile
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROFILE_DIR = os.path.join(PROJECT_DIR, "voice_profile")
PYTHON_BIN = os.path.join(PROJECT_DIR, ".venv-cloner", "bin", "python")

SAMPLE_WAV = os.path.join(PROFILE_DIR, "my_voice.wav")
SAMPLE_TXT = os.path.join(PROFILE_DIR, "my_voice.txt")

if len(sys.argv) < 2:
    sys.exit(0)

text_to_speak = " ".join(sys.argv[1:]).strip()
if not text_to_speak:
    sys.exit(0)

# Check if user has cloned their voice
if os.path.exists(SAMPLE_WAV) and os.path.getsize(SAMPLE_WAV) > 1000:
    ref_text = "Hello, this is my personal AI assistant AU running offline on my Mac."
    if os.path.exists(SAMPLE_TXT):
        try:
            with open(SAMPLE_TXT, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    ref_text = content
        except Exception:
            pass

    sys.stderr.write(f"🗣️ [AU Voice: ⭐ YOUR CLONED MLX VOICE]\n")
    sys.stderr.flush()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_wav = tmp.name

    try:
        cmd = [
            PYTHON_BIN, "-m", "f5_tts_mlx.generate",
            "--text", text_to_speak,
            "--ref-audio", SAMPLE_WAV,
            "--ref-text", ref_text,
            "--steps", "16",
            "--q", "8",
            "--output", out_wav
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 500:
            subprocess.run(["afplay", out_wav])
            os.remove(out_wav)
            sys.exit(0)
    except Exception:
        if os.path.exists(out_wav):
            try:
                os.remove(out_wav)
            except Exception:
                pass

# Fallback to AU app bundle / system voice
au_app = "/Applications/AU.app/Contents/MacOS/AU"
if os.path.exists(au_app):
    subprocess.run([au_app, "--speak", text_to_speak])
else:
    subprocess.run(["say", text_to_speak])
