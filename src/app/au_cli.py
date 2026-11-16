#!/usr/bin/env python3
"""
AU Unix Pipeline CLI Tool
Adapted from Gemini-CLI & Aider terminal architecture.

Allows AU to be used directly from the Terminal with Unix stdin/stdout piping:
  cat file.py | au "explain what this code does"
  git diff | au "generate a conventional git commit message"
  au "check my system status"
  au --code "add error handling to main.swift"
  au --commit "refactored audio stitching"
"""

import os
import sys
import json
import urllib.request
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import au_tools
import au_memory
from au_repo_map import get_compact_repo_map

OLLAMA_URL = "http://localhost:11434/api/chat"

def query_chat(messages: list, model: str = "au-assistant:latest", timeout: int = 40) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"Error reaching local brain: {e}"

def main():
    parser = argparse.ArgumentParser(
        description="AU Terminal CLI — Private AI & macOS Automation Agent",
        epilog="Examples:\n  cat file.py | au 'explain this'\n  git diff | au 'generate commit message'\n  au --code 'fix syntax in file.py'"
    )
    parser.add_argument("prompt", nargs="*", help="Instruction or query for AU")
    parser.add_argument("--code", action="store_true", help="Activate Code Architect mode with repo map")
    parser.add_argument("--research", action="store_true", help="Activate Research Partner mode")
    parser.add_argument("--commit", action="store_true", help="Automatically commit modified files to git upon completion")
    parser.add_argument("--voice", action="store_true", help="Speak the response out loud using au-speak")
    parser.add_argument("--model", type=str, default=None, help="Override local Ollama model")

    args = parser.parse_args()

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

    # Determine persona & model
    if args.research:
        model = args.model or "au-notebooklm:latest"
        persona_desc = "You are AU in Research Partner mode. Ground answers thoroughly in facts and provide concise, rigorous summaries."
    elif args.code:
        model = args.model or "au-assistant:latest"
        repo_map = get_compact_repo_map(".")
        persona_desc = (
            "You are AU in Code Architect mode. You specialize in software engineering, bash commands, and precision diffs.\n"
            f"{repo_map}\n"
            "When modifying files, prefer [ACTION: edit_file_patch(\"path\", \"search_block\", \"replace_block\")]."
        )
    else:
        model = args.model or "au-assistant:latest"
        persona_desc = "You are AU, the user's personal, highly intelligent AI assistant controlling their Mac."

    # Memory grounding
    mem_engine = au_memory.AUMemoryEngine()
    mem_context = mem_engine.format_context_prompt(full_prompt)

    system_prompt = (
        f"{persona_desc}\n"
        "Available actions:\n"
        "- [ACTION: open_app(\"App Name\")]\n"
        "- [ACTION: close_app(\"App Name\")]\n"
        "- [ACTION: set_volume(percentage_0_to_100)]\n"
        "- [ACTION: get_battery()]\n"
        "- [ACTION: get_disk_space()]\n"
        "- [ACTION: get_system_status()]\n"
        "- [ACTION: take_screenshot()]\n"
        "- [ACTION: create_note(\"Title\", \"Content\")]\n"
        "- [ACTION: browse_url(\"https://...\")]\n"
        "- [ACTION: search_web_summary(\"query\")]\n"
        "- [ACTION: read_file(\"path\")]\n"
        "- [ACTION: write_file(\"path\", \"content\")]\n"
        "- [ACTION: edit_file_patch(\"path\", \"search_block\", \"replace_block\")]\n"
        "- [ACTION: verify_syntax(\"path\")]\n"
        "- [ACTION: execute_bash(\"command\")]\n"
        "\nProvide clear, direct, and concise output.\n"
        + mem_context
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_prompt}
    ]

    max_steps = 4
    for step in range(max_steps):
        raw_res = query_chat(messages, model=model)
        clean_text, executed, tool_results = au_tools.parse_and_execute_all(raw_res)

        if not executed:
            final_output = clean_text or raw_res
            print(final_output)

            # Auto-commit if requested
            if args.commit:
                commit_res = au_tools.run_git_auto_commit(au_tools.GitAutoCommitArgs(message=user_query or "task completed"))
                print(f"\n📦 {commit_res.message}")

            # Voice output if requested
            if args.voice:
                speak_tool = os.path.join(SCRIPT_DIR, "..", "..", "tools", "au-speak")
                if os.path.exists(speak_tool):
                    import subprocess
                    subprocess.run([speak_tool, final_output])

            return

        # Print executed action logs
        for act in executed:
            print(f"⚡ [AU ACTION]: {act}", file=sys.stderr)

        observation_str = "Observation: " + " | ".join(executed)
        messages.append({"role": "assistant", "content": raw_res})
        messages.append({"role": "user", "content": f"{observation_str}\nNow provide the final response or next step."})

    if clean_text:
        print(clean_text)

if __name__ == "__main__":
    main()
