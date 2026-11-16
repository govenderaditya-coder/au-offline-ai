#!/usr/bin/env python3
"""
AU Unix Pipeline CLI Tool & Orchestrator Dispatcher
Allows AU to be used directly from the Terminal with Unix stdin/stdout piping,
routed through the central AUOrchestrator core task queue.

Examples:
  cat file.py | au "explain what this code does"
  git diff | au "generate a conventional git commit message"
  au "what is my battery level"
  au --code "fix syntax in au_voice_id.py"
  au --research "summarize my offline ai architecture"
  au --status
  au --queue
  au --purge
"""

import os
import sys
import json
import argparse
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from au_orchestrator import AUOrchestrator, AUTask, TaskStatus, MemoryCost, TaskPriority
import au_tools

def main():
    parser = argparse.ArgumentParser(
        description="AU Terminal CLI — Private AI & macOS Automation Agent (Orchestrated)",
        epilog="Examples:\n  cat file.py | au 'explain this'\n  git diff | au 'generate commit message'\n  au --code 'fix file.py'\n  au --status"
    )
    parser.add_argument("prompt", nargs="*", help="Instruction or query for AU")
    parser.add_argument("--code", action="store_true", help="Dispatch task to Code Architect layer")
    parser.add_argument("--research", action="store_true", help="Dispatch task to Document Search / Research layer")
    parser.add_argument("--commit", action="store_true", help="Automatically commit modified files to git upon completion")
    parser.add_argument("--voice", action="store_true", help="Speak the response out loud using au-speak")
    parser.add_argument("--status", action="store_true", help="Show M4 Unified RAM telemetry & task queue status")
    parser.add_argument("--queue", action="store_true", help="List recent tasks in the orchestrator queue")
    parser.add_argument("--purge", action="store_true", help="Unload idle models from VRAM and free Unified Memory")
    parser.add_argument("--model", type=str, default=None, help="Override local model name")

    args = parser.parse_args()
    orchestrator = AUOrchestrator()

    # Management commands
    if args.status:
        status = orchestrator.get_status_overview()
        mem = status["memory"]
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"🧠 AU Central Orchestrator (Apple Silicon M4)")
        print(f"📊 Memory Status: [{mem['state']}] Used: {mem['used_gb']} GB / Available: {mem['available_gb']} GB (Total: {mem['total_gb']} GB)")
        print(f"⚡ VRAM Resident Models: {status['running_models'] or 'None (Lazy Unloaded)'}")
        print(f"📋 Task Queue: {status['active_tasks_count']} running, {status['queued_tasks_count']} queued, {status['paused_tasks_count']} paused")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return

    if args.queue:
        tasks = orchestrator.queue.list_tasks(limit=15)
        print(f"📋 Recent Orchestrator Tasks ({len(tasks)}):")
        for t in tasks:
            print(f" • [{t.status.upper():9}] [{t.layer:15}] ({t.memory_cost:6}) {t.id} -> {t.prompt[:50]}")
        return

    if args.purge:
        orchestrator.router.unload_idle_models()
        orchestrator.governor.purge_memory()
        print("🧹 Memory purged: idle models unloaded from Unified RAM.")
        return

    # Read piped stdin if present
    stdin_content = ""
    if not sys.stdin.isatty():
        try:
            stdin_content = sys.stdin.read().strip()
        except Exception:
            pass

    user_query = " ".join(args.prompt).strip()

    if not user_query and not stdin_content:
        parser.print_help()
        sys.exit(0)

    # Combine stdin and prompt
    full_prompt = user_query
    if stdin_content:
        if full_prompt:
            full_prompt = f"{full_prompt}\n\n[INPUT DATA]:\n{stdin_content}"
        else:
            full_prompt = f"Analyze and respond to this input:\n\n{stdin_content}"

    # Determine domain layer & memory cost
    if args.research:
        layer = "document_search"
        memory_cost = MemoryCost.MEDIUM
    elif args.code:
        layer = "coding"
        memory_cost = MemoryCost.MEDIUM
    else:
        # Default chat / system layer
        layer = "chat"
        memory_cost = MemoryCost.LOW

    # Create & submit task through Orchestrator Queue
    task = AUTask(
        layer=layer,
        prompt=full_prompt,
        payload={
            "stdin": stdin_content,
            "commit": args.commit,
            "model": args.model
        },
        priority=TaskPriority.URGENT,
        memory_cost=memory_cost
    )
    orchestrator.queue.submit(task)

    # Dispatch through Core Hub
    completed_task = orchestrator.dispatch(task)

    if completed_task.status == TaskStatus.PAUSED:
        print(f"⏸️ [TASK PAUSED]: {completed_task.error}")
        return

    if completed_task.status == TaskStatus.FAILED:
        print(f"❌ [TASK ERROR]: {completed_task.error}", file=sys.stderr)
        return

    result_data = completed_task.result or {}
    final_output = result_data.get("text", "")

    # Print any actions executed by coding / system handlers
    if "actions" in result_data:
        for act in result_data["actions"]:
            print(f"⚡ [AU ACTION]: {act}", file=sys.stderr)

    if final_output:
        print(final_output)

    # Auto-commit if requested and not handled inside layer
    if args.commit and layer != "coding":
        commit_res = au_tools.run_git_auto_commit(au_tools.GitAutoCommitArgs(message=user_query or "task completed"))
        print(f"\n📦 {commit_res.message}")

    # Voice output if requested
    if args.voice and final_output:
        speak_tool = os.path.join(SCRIPT_DIR, "..", "..", "tools", "au-speak")
        if os.path.exists(speak_tool):
            subprocess.run([speak_tool, final_output])

if __name__ == "__main__":
    main()
