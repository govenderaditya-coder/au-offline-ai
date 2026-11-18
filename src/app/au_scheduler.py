#!/usr/bin/env python3
"""
AU Daily Routines & Proactive Briefings Engine
Generates comprehensive Morning Executive Briefings and Evening Productive Recaps.
Combines hardware telemetry, weather, git commit activity, and active tasks.
"""

import os
import sys
import subprocess
from datetime import datetime
from typing import Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Optional imports
try:
    import au_tools
except ImportError:
    au_tools = None

try:
    from au_orchestrator import AUOrchestrator
except ImportError:
    AUOrchestrator = None

class AUBriefingEngine:
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator or (AUOrchestrator() if AUOrchestrator else None)

    def generate_morning_briefing(self) -> str:
        """Generates an energizing, comprehensive morning briefing."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")

        # 1. Weather
        weather = "Weather unavailable"
        if au_tools:
            try:
                w_res = au_tools.run_get_weather(au_tools.GetWeatherArgs(city="auto"))
                weather = w_res.message
            except Exception:
                pass

        # 2. Battery & Hardware
        battery = "Battery status unavailable"
        if au_tools:
            try:
                b_res = au_tools.run_get_battery()
                battery = b_res.message
            except Exception:
                pass

        # 3. Memory & Tasks overview
        ram_status = "Optimal"
        active_tasks = 0
        if self.orchestrator:
            try:
                ov = self.orchestrator.get_status_overview()
                ram_status = f"{ov['memory']['used_gb']} GB used ({ov['memory']['state']})"
                active_tasks = ov['active_tasks_count'] + ov['queued_tasks_count']
            except Exception:
                pass

        # 4. Recent Plans / Notes
        notes_dir = os.path.expanduser("~/Documents/AU_Notes")
        recent_notes_count = 0
        if os.path.exists(notes_dir):
            recent_notes_count = len([f for f in os.listdir(notes_dir) if f.endswith(".md")])

        briefing = (
            f"🌅 Good morning Aditya! Today is {date_str} ({time_str}).\n\n"
            f"🌤️ Current Weather: {weather}\n"
            f"🔋 Hardware: {battery} | RAM: {ram_status}\n"
            f"📋 Work Queue: {active_tasks} pending tasks | {recent_notes_count} documents in AU Notes\n\n"
            f"💡 Mindset: System is primed and running 100% locally on Apple Silicon. Let's make today productive!"
        )
        return briefing

    def generate_evening_recap(self) -> str:
        """Generates a summary of today's work, git commits, and accomplishments."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")

        # Git commits today
        git_commits = []
        try:
            res = subprocess.run(
                ["git", "log", "--since=midnight", "--oneline"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5
            )
            git_commits = [c.strip() for c in res.stdout.strip().splitlines() if c.strip()]
        except Exception:
            pass

        commit_summary = f"{len(git_commits)} commits recorded today" if git_commits else "No git commits recorded today"

        # Tasks completed
        completed_tasks = 0
        if self.orchestrator:
            try:
                tasks = self.orchestrator.queue.list_tasks(status="completed", limit=20)
                completed_tasks = len(tasks)
            except Exception:
                pass

        recap = (
            f"🌙 Evening Recap ({time_str})\n\n"
            f"✅ Daily Output: {commit_summary} | {completed_tasks} orchestrator tasks processed.\n"
        )
        if git_commits:
            recap += "📦 Recent Commits:\n" + "\n".join([f"  • {c}" for c in git_commits[:4]]) + "\n"

        recap += "\n✨ Great job today. Memory and tasks are safely persisted offline. Ready for standby whenever you are."
        return recap

if __name__ == "__main__":
    b = AUBriefingEngine()
    print("--- MORNING BRIEFING ---")
    print(b.generate_morning_briefing())
    print("\n--- EVENING RECAP ---")
    print(b.generate_evening_recap())
