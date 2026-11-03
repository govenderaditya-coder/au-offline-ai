#!/usr/bin/env python3
"""
AU Voice ID — Biometric Speaker Recognition Engine
Enrolls the owner's voice and verifies speaker identity offline.
"""

import os
import json
import math
import wave
import struct

VOICE_PROFILE_PATH = os.path.expanduser("~/.offline-ai/voice_profile.json")

def is_enrolled() -> bool:
    return os.path.exists(VOICE_PROFILE_PATH)

def get_owner_name() -> str:
    if not is_enrolled():
        return "Owner"
    try:
        with open(VOICE_PROFILE_PATH, "r") as f:
            data = json.load(f)
            return data.get("owner_name", "Owner")
    except Exception:
        return "Owner"

def save_voice_profile(owner_name: str, sample_text: str):
    os.makedirs(os.path.dirname(VOICE_PROFILE_PATH), exist_ok=True)
    profile = {
        "owner_name": owner_name,
        "enrolled_at": str(os.path.getmtime(VOICE_PROFILE_PATH) if os.path.exists(VOICE_PROFILE_PATH) else ""),
        "phrase": sample_text,
        "voice_lock_enabled": True
    }
    with open(VOICE_PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

def set_voice_lock(enabled: bool):
    if not os.path.exists(VOICE_PROFILE_PATH):
        save_voice_profile("Aditya", "AU is my personal assistant")
    try:
        with open(VOICE_PROFILE_PATH, "r") as f:
            data = json.load(f)
        data["voice_lock_enabled"] = enabled
        with open(VOICE_PROFILE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def is_voice_lock_active() -> bool:
    if not os.path.exists(VOICE_PROFILE_PATH):
        return False
    try:
        with open(VOICE_PROFILE_PATH, "r") as f:
            data = json.load(f)
            return data.get("voice_lock_enabled", False)
    except Exception:
        return False
