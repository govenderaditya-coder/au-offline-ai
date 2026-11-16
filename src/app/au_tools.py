#!/usr/bin/env python3
"""
AU NextGen Type-Safe Tool & Action Engine
Conforms to Model Context Protocol (MCP) tool schemas and Pydantic v2 validation.
Combines Pydantic-AI validation with OpenHands Observation/Action execution patterns.
"""

import os
import re
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, Field, ValidationError

# App aliases for natural language mappings
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

# ==============================================================================
# Pydantic Tool Schemas
# ==============================================================================

class SetVolumeArgs(BaseModel):
    volume: int = Field(..., ge=0, le=100, description="Volume level from 0 to 100")

class OpenAppArgs(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name of the macOS application to open")

class CloseAppArgs(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name of the macOS application to close")

class MediaControlArgs(BaseModel):
    command: Literal["play", "pause", "playpause", "next", "prev", "skip"] = Field(
        ..., description="Media command to send to Spotify or Apple Music"
    )

class SearchWebArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Search query string for web search")

class OpenUrlArgs(BaseModel):
    url: str = Field(..., min_length=3, description="Web URL to open in default browser")

class TakeScreenshotArgs(BaseModel):
    filename: Optional[str] = Field(None, description="Optional custom filename for screenshot")

class CreateNoteArgs(BaseModel):
    title: str = Field(..., min_length=1, description="Title of the note")
    content: str = Field(..., description="Markdown body content of the note")

class OpenPathArgs(BaseModel):
    path: str = Field(..., description="File or folder path to open in Finder")

class ExecuteBashArgs(BaseModel):
    command: str = Field(..., description="Terminal shell command to execute")
    timeout_seconds: Optional[int] = Field(15, ge=1, le=60, description="Timeout in seconds")

class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path of file to read")
    max_lines: Optional[int] = Field(200, ge=1, le=1000, description="Maximum lines to read")

class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path of file to write")
    content: str = Field(..., description="Content to write into the file")
    append: Optional[bool] = Field(False, description="Whether to append instead of overwrite")

# ==============================================================================
# Execution Handlers
# ==============================================================================

class ToolResult(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

def run_set_volume(args: SetVolumeArgs) -> ToolResult:
    vol = args.volume
    proc = subprocess.run(["osascript", "-e", f"set volume output volume {vol}"], capture_output=True, text=True)
    if proc.returncode == 0:
        return ToolResult(success=True, message=f"Volume set to {vol}%", data={"volume": vol})
    return ToolResult(success=False, message=f"Failed to set volume: {proc.stderr}")

def run_open_app(args: OpenAppArgs) -> ToolResult:
    target = resolve_app(args.app_name)
    proc = subprocess.run(["open", "-a", target], capture_output=True, text=True)
    if proc.returncode == 0:
        return ToolResult(success=True, message=f"Opened {target}", data={"app": target})
    return ToolResult(success=False, message=f"Could not open {target}: {proc.stderr}")

def run_close_app(args: CloseAppArgs) -> ToolResult:
    target = resolve_app(args.app_name)
    script = f'tell application "{target}" to quit'
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode == 0:
        return ToolResult(success=True, message=f"Closed {target}", data={"app": target})
    return ToolResult(success=False, message=f"Could not close {target}: {proc.stderr}")

def run_media_control(args: MediaControlArgs) -> ToolResult:
    cmd = args.command
    is_spotify = subprocess.run(["pgrep", "-x", "Spotify"], capture_output=True).returncode == 0
    target = "Spotify" if is_spotify else "Music"

    if cmd in ("play", "pause", "playpause"):
        action = "playpause"
    elif cmd in ("next", "skip"):
        action = "next track"
    elif cmd == "prev":
        action = "previous track"
    else:
        action = "playpause"

    script = f'tell application "{target}" to {action}'
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode == 0:
        return ToolResult(success=True, message=f"Media {cmd} sent to {target}", data={"target": target, "command": cmd})
    return ToolResult(success=False, message=f"Media control failed on {target}")

def run_search_web(args: SearchWebArgs) -> ToolResult:
    query_encoded = args.query.replace(" ", "+")
    url = f"https://www.google.com/search?q={query_encoded}"
    subprocess.run(["open", url], capture_output=True)
    return ToolResult(success=True, message=f"Searching Google for '{args.query}'", data={"query": args.query})

def run_open_url(args: OpenUrlArgs) -> ToolResult:
    url = args.url
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    subprocess.run(["open", url], capture_output=True)
    return ToolResult(success=True, message=f"Opened {url}", data={"url": url})

def run_get_battery() -> ToolResult:
    proc = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    m = re.search(r'(\d+%)', proc.stdout)
    pct = m.group(1) if m else "Unknown"
    is_charging = "charging" in proc.stdout.lower() or "ac power" in proc.stdout.lower()
    state = "charging" if is_charging else "on battery"
    msg = f"Battery is at {pct} ({state})"
    return ToolResult(success=True, message=msg, data={"percentage": pct, "charging": is_charging})

def run_get_disk_space() -> ToolResult:
    proc = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
    lines = proc.stdout.strip().split("\n")
    if len(lines) > 1:
        parts = lines[1].split()
        free, total = parts[3], parts[1]
        msg = f"Disk Space: {free} free out of {total}"
        return ToolResult(success=True, message=msg, data={"free": free, "total": total})
    return ToolResult(success=False, message="Could not read disk space")

def run_get_system_status() -> ToolResult:
    now_str = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    batt = run_get_battery().message
    disk = run_get_disk_space().message
    msg = f"{now_str}. {batt}. {disk}."
    return ToolResult(success=True, message=msg, data={"time": now_str})

def run_take_screenshot(args: TakeScreenshotArgs) -> ToolResult:
    desktop = os.path.expanduser("~/Desktop")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    fname = args.filename or f"AU_Screenshot_{ts}.png"
    if not fname.endswith(".png"):
        fname += ".png"
    dest = os.path.join(desktop, fname)
    proc = subprocess.run(["screencapture", "-x", dest], capture_output=True)
    if proc.returncode == 0:
        return ToolResult(success=True, message=f"Screenshot saved to Desktop: {fname}", data={"path": dest})
    return ToolResult(success=False, message="Screenshot capture failed")

def run_create_note(args: CreateNoteArgs) -> ToolResult:
    notes_dir = os.path.expanduser("~/Documents/AU_Notes")
    os.makedirs(notes_dir, exist_ok=True)
    clean_title = re.sub(r'[^\w\-_\. ]', '_', args.title).strip() or "Untitled"
    file_path = os.path.join(notes_dir, f"{clean_title}.md")
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    content = f"# {args.title}\n\n*Created by AU on {timestamp}*\n\n{args.content}\n"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    subprocess.run(["open", file_path], capture_output=True)
    return ToolResult(success=True, message=f"Created note '{args.title}' in AU_Notes", data={"path": file_path})

def run_open_path(args: OpenPathArgs) -> ToolResult:
    expanded = os.path.expanduser(args.path.strip())
    if os.path.exists(expanded):
        subprocess.run(["open", expanded], capture_output=True)
        return ToolResult(success=True, message=f"Opened {expanded}", data={"path": expanded})
    return ToolResult(success=False, message=f"Path does not exist: {expanded}")

# Block dangerous shell operations for security
BLOCKED_COMMANDS = ["rm -rf /", "rm -rf ~", "mkfs", "dd if=", ":(){ :|:& };:"]

def run_execute_bash(args: ExecuteBashArgs) -> ToolResult:
    cmd = args.command.strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd:
            return ToolResult(success=False, message=f"Command rejected for safety: dangerous pattern '{blocked}'")

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=args.timeout_seconds or 15
        )
        output = proc.stdout.strip()
        err = proc.stderr.strip()
        combined = output if output else err
        if not combined:
            combined = f"Command finished with exit code {proc.returncode}"
        
        # Truncate if output is too long for voice/UI
        if len(combined) > 500:
            combined = combined[:500] + "... [truncated]"

        return ToolResult(
            success=(proc.returncode == 0),
            message=combined,
            data={"returncode": proc.returncode, "stdout": output, "stderr": err}
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, message=f"Command timed out after {args.timeout_seconds}s")
    except Exception as e:
        return ToolResult(success=False, message=f"Execution error: {e}")

def run_read_file(args: ReadFileArgs) -> ToolResult:
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(args.max_lines or 200)]
            content = "".join(lines)
        return ToolResult(success=True, message=f"Read {len(lines)} lines from {os.path.basename(path)}", data={"content": content})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed reading file: {e}")

def run_write_file(args: WriteFileArgs) -> ToolResult:
    path = os.path.expanduser(args.path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        mode = "a" if args.append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(args.content)
        action_word = "Appended to" if args.append else "Wrote"
        return ToolResult(success=True, message=f"{action_word} {path} successfully", data={"path": path})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed writing file: {e}")

# ==============================================================================
# Model Context Protocol (MCP) Registry
# ==============================================================================

TOOL_REGISTRY = {
    "set_volume": (SetVolumeArgs, run_set_volume, "Adjust the macOS output audio volume (0 to 100)"),
    "open_app": (OpenAppArgs, run_open_app, "Launch or activate a macOS application by name"),
    "close_app": (CloseAppArgs, run_close_app, "Quit a running macOS application"),
    "media_control": (MediaControlArgs, run_media_control, "Control playback (play, pause, next, prev) on Spotify or Music"),
    "search_web": (SearchWebArgs, run_search_web, "Search Google in the default browser"),
    "open_url": (OpenUrlArgs, run_open_url, "Open a web URL in the browser"),
    "get_battery": (None, run_get_battery, "Check MacBook battery percentage and power source"),
    "get_disk_space": (None, run_get_disk_space, "Check Mac available disk space"),
    "get_system_status": (None, run_get_system_status, "Get consolidated status: current time, battery, and free disk space"),
    "take_screenshot": (TakeScreenshotArgs, run_take_screenshot, "Capture a screenshot and save it to Desktop"),
    "create_note": (CreateNoteArgs, run_create_note, "Create a markdown note in Documents/AU_Notes"),
    "open_path": (OpenPathArgs, run_open_path, "Open a folder or file in macOS Finder"),
    "execute_bash": (ExecuteBashArgs, run_execute_bash, "Safely execute a shell command on macOS and inspect output"),
    "read_file": (ReadFileArgs, run_read_file, "Read text from a local file"),
    "write_file": (WriteFileArgs, run_write_file, "Write text to a local file"),
}

def get_mcp_tools() -> List[Dict[str, Any]]:
    """Generates standard Model Context Protocol (MCP) tool declarations."""
    tools = []
    for name, (schema_cls, _, desc) in TOOL_REGISTRY.items():
        input_schema = schema_cls.model_json_schema() if schema_cls else {"type": "object", "properties": {}}
        tools.append({
            "name": name,
            "description": desc,
            "inputSchema": input_schema
        })
    return tools

def execute_tool_by_name(tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
    """Executes a tool by name with validated Pydantic arguments."""
    tool_key = tool_name.strip().lower()
    if tool_key not in TOOL_REGISTRY:
        return ToolResult(success=False, message=f"Unknown tool: '{tool_name}'")

    schema_cls, func, _ = TOOL_REGISTRY[tool_key]
    try:
        if schema_cls:
            validated_args = schema_cls(**arguments)
            return func(validated_args)
        else:
            return func()
    except ValidationError as ve:
        error_details = "; ".join([f"{e['loc']}: {e['msg']}" for e in ve.errors()])
        return ToolResult(success=False, message=f"Invalid arguments for {tool_name}: {error_details}")
    except Exception as e:
        return ToolResult(success=False, message=f"Tool error during {tool_name}: {e}")

# ==============================================================================
# Universal Multi-Format Tool Parser
# Parses: 1) JSON tool blocks, 2) Markdown code blocks, 3) Legacy [ACTION: ...] tags
# ==============================================================================

def parse_and_execute_all(raw_text: str) -> tuple[str, List[str], List[ToolResult]]:
    """
    Parses tool calls in any supported format (JSON or legacy ACTION tags),
    executes them safely, and returns (clean_text, action_strings, tool_results).
    """
    clean_text = raw_text
    executed_strings: List[str] = []
    tool_results: List[ToolResult] = []

    # 1. Parse JSON tool calls e.g. {"tool": "name", "parameters": {...}}
    json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
    if not json_blocks:
        # Check raw un-fenced json
        json_matches = re.finditer(r'\{[\s\n]*"(?:tool|action|name)"\s*:\s*".*?\}', raw_text, re.DOTALL)
        json_blocks = [m.group(0) for m in json_matches]

    for block in json_blocks:
        try:
            data = json.loads(block)
            name = data.get("tool") or data.get("action") or data.get("name")
            params = data.get("parameters") or data.get("arguments") or data.get("params") or {}
            if name:
                res = execute_tool_by_name(name, params)
                tool_results.append(res)
                executed_strings.append(res.message)
                clean_text = clean_text.replace(block, "")
        except Exception:
            pass

    # 2. Parse legacy [ACTION: ...] tags for 100% backward compatibility
    action_matches = re.findall(r'\[ACTION:\s*(.*?)\]', clean_text, re.IGNORECASE)
    for act_str in action_matches:
        res = _execute_legacy_action(act_str)
        tool_results.append(res)
        executed_strings.append(res.message)

    # Strip tags and clean markdown artifacts from speech
    clean_text = re.sub(r'\[ACTION:\s*.*?\]', '', clean_text)
    clean_text = re.sub(r'```(?:json)?.*?```', '', clean_text, flags=re.DOTALL)
    clean_text = clean_text.strip()

    return clean_text, executed_strings, tool_results

def _execute_legacy_action(action_str: str) -> ToolResult:
    """Dispatches legacy string tags into type-safe Pydantic tools."""
    action_str = action_str.strip()

    # open_app("Spotify")
    m = re.match(r'open_app\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_open_app(OpenAppArgs(app_name=m.group(1)))

    # close_app("Spotify")
    m = re.match(r'close_app\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_close_app(CloseAppArgs(app_name=m.group(1)))

    # set_volume(50)
    m = re.match(r'set_volume\((\d+)\)', action_str, re.IGNORECASE)
    if m:
        return run_set_volume(SetVolumeArgs(volume=int(m.group(1))))

    # media_control("next")
    m = re.match(r'media_control\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        cmd = m.group(1).lower()
        if cmd in ("play", "pause", "playpause", "next", "prev", "skip"):
            return run_media_control(MediaControlArgs(command=cmd)) # type: ignore

    # search_web("query")
    m = re.match(r'search_web\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_search_web(SearchWebArgs(query=m.group(1)))

    # open_url("https://...")
    m = re.match(r'open_url\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_open_url(OpenUrlArgs(url=m.group(1)))

    # get_battery
    if "get_battery" in action_str.lower():
        return run_get_battery()

    # get_disk_space
    if "get_disk" in action_str.lower():
        return run_get_disk_space()

    # get_time / status
    if "get_time" in action_str.lower() or "status" in action_str.lower():
        return run_get_system_status()

    # take_screenshot
    if "take_screenshot" in action_str.lower():
        return run_take_screenshot(TakeScreenshotArgs())

    # create_note("title", "content")
    m = re.match(r'create_note\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_create_note(CreateNoteArgs(title=m.group(1), content=m.group(2)))

    # open_folder("path")
    m = re.match(r'open_folder\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_open_path(OpenPathArgs(path=m.group(1)))

    # Fallback to safe bash execution
    return run_execute_bash(ExecuteBashArgs(command=action_str))

if __name__ == "__main__":
    print("Testing AU NextGen Tool Engine...")
    print(f"Total MCP Tools Registered: {len(TOOL_REGISTRY)}")
    for t in get_mcp_tools():
        print(f"  • {t['name']}: {t['description']}")

    # Quick test
    sample_text = "Checking system status. [ACTION: get_battery()] Setting volume. [ACTION: set_volume(45)]"
    speech, acts, results = parse_and_execute_all(sample_text)
    print("\nParsed speech:", speech)
    print("Executed actions:", acts)
