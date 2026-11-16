#!/usr/bin/env python3
"""
AU Personal Assistant — Mac Action Dispatcher (Backward-Compatible Bridge)
Directs all action and tool calls to the type-safe Pydantic/MCP engine in au_tools.py.
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import au_tools

def execute_action(action_str: str) -> str:
    """Executes a parsed action string and returns a user-facing result string."""
    res = au_tools._execute_legacy_action(action_str)
    return res.message

def parse_and_execute(response_text: str) -> tuple[str, list[str]]:
    """
    Extracts all action tags and JSON tool calls from response,
    executes them safely, and returns (clean_spoken_text, list_of_executed_actions).
    """
    clean_speech, executed_actions, _ = au_tools.parse_and_execute_all(response_text)
    return clean_speech, executed_actions

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_input = " ".join(sys.argv[1:])
        speech, actions = parse_and_execute(test_input)
        print("Actions executed:", actions)
        print("Speech output:", speech)
