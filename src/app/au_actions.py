#!/usr/bin/env python3
"""
AU Personal Assistant — Mac Action Dispatcher
Parses action tags from AU responses and executes them natively on macOS.
"""

import os
import re
import sys
import time
import subprocess
from datetime import datetime

APP_ALIASES = {
    "spotify": "Spotify",
    "brave": "Brave Browser",
    "browser": "Brave Browser",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "notes": "Notes",
    "calculator": "Calculator",
    "calc": "Calculator",
    "finder": "Finder",
    "calendar": "Calendar",
    "mail": "Mail",
    "music": "Music",
    "messages": "Messages",
    "imessage": "Messages",
    "settings": "System Settings",
    "system preferences": "System Settings",
}

def resolve_app(name: str) -> str:
    cleaned = name.strip().lower()
    return APP_ALIASES.get(cleaned, name.strip())

def execute_action(action_str: str) -> str:
    """Executes a parsed action and returns an optional execution note."""
    action_str = action_str.strip()
    
    # open_app("Name")
    m = re.match(r'open_app\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        app_name = resolve_app(m.group(1))
        subprocess.run(["open", "-a", app_name], capture_output=True)
        return f"Opened {app_name}"

    # close_app("Name")
    m = re.match(r'close_app\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        app_name = resolve_app(m.group(1))
        subprocess.run(["osascript", "-e", f'tell application "{app_name}" to quit'], capture_output=True)
        return f"Closed {app_name}"

    # set_volume(percentage)
    m = re.match(r'set_volume\((\d+)\)', action_str, re.IGNORECASE)
    if m:
        vol = max(0, min(100, int(m.group(1))))
        subprocess.run(["osascript", "-e", f"set volume output volume {vol}"], capture_output=True)
        return f"Volume set to {vol}%"

    # media_control("play" | "pause" | "next" | "prev")
    m = re.match(r'media_control\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        cmd = m.group(1).lower()
        # Check Spotify first
        is_spotify = subprocess.run(["pgrep", "-x", "Spotify"], capture_output=True).returncode == 0
        target = "Spotify" if is_spotify else "Music"
        if cmd in ("play", "pause", "playpause"):
            subprocess.run(["osascript", "-e", f'tell application "{target}" to playpause'], capture_output=True)
        elif cmd in ("next", "next track", "skip"):
            subprocess.run(["osascript", "-e", f'tell application "{target}" to next track'], capture_output=True)
        elif cmd in ("prev", "previous", "previous track"):
            subprocess.run(["osascript", "-e", f'tell application "{target}" to previous track'], capture_output=True)
        return f"Media {cmd} sent to {target}"

    # search_web("query")
    m = re.match(r'search_web\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        query = m.group(1).replace(" ", "+")
        subprocess.run(["open", f"https://www.google.com/search?q={query}"], capture_output=True)
        return f"Searching Google for {m.group(1)}"

    # open_url("https://...")
    m = re.match(r'open_url\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://" + url
        subprocess.run(["open", url], capture_output=True)
        return f"Opened {url}"

    # get_battery()
    if "get_battery" in action_str.lower():
        res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
        batt_match = re.search(r'(\d+%)', res.stdout)
        batt_pct = batt_match.group(1) if batt_match else "unknown"
        state = "charging" if "charging" in res.stdout else "on battery"
        return f"Battery is at {batt_pct} ({state})"

    # get_disk_space()
    if "get_disk" in action_str.lower():
        res = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            return f"You have {parts[3]} free out of {parts[1]}"
        return "Disk info retrieved"

    # get_time()
    if "get_time" in action_str.lower():
        now = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
        return f"The current time is {now}"

    # take_screenshot()
    if "take_screenshot" in action_str.lower():
        desktop = os.path.expanduser("~/Desktop")
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = os.path.join(desktop, f"AU_Screenshot_{ts}.png")
        subprocess.run(["screencapture", "-x", file_path], capture_output=True)
        return f"Screenshot saved to Desktop: AU_Screenshot_{ts}.png"

    # create_note("Title", "Content")
    m = re.match(r'create_note\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        title, content = m.group(1), m.group(2)
        notes_dir = os.path.expanduser("~/Documents/AU_Notes")
        os.makedirs(notes_dir, exist_ok=True)
        clean_title = re.sub(r'[^\w\-_\. ]', '_', title).strip() or "Untitled"
        file_path = os.path.join(notes_dir, f"{clean_title}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n*Created by AU on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{content}\n")
        subprocess.run(["open", file_path], capture_output=True)
        return f"Created note '{title}' in AU_Notes"

    # open_folder("path")
    m = re.match(r'open_folder\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        path = os.path.expanduser(m.group(1).strip())
        subprocess.run(["open", path], capture_output=True)
        return f"Opened folder {path}"

    return "No action matched"

def parse_and_execute(response_text: str) -> tuple[str, list[str]]:
    """
    Extracts all [ACTION: ...] tags from response, executes them,
    and returns (clean_spoken_text, list_of_executed_actions).
    """
    action_matches = re.findall(r'\[ACTION:\s*(.*?)\]', response_text)
    executed = []
    for act in action_matches:
        result = execute_action(act)
        executed.append(result)

    # Strip action tags for clean spoken/chat output
    clean_speech = re.sub(r'\[ACTION:\s*.*?\]', '', response_text).strip()
    return clean_speech, executed

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_input = " ".join(sys.argv[1:])
        speech, actions = parse_and_execute(test_input)
        print("Actions executed:", actions)
        print("Speech output:", speech)
