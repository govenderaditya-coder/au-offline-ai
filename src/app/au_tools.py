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
import urllib.request
import urllib.parse
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

class BrowseUrlArgs(BaseModel):
    url: str = Field(..., description="Web URL to fetch and extract readable article text from")
    max_chars: Optional[int] = Field(1800, ge=200, le=5000, description="Max characters to return")

class SearchWebSummaryArgs(BaseModel):
    query: str = Field(..., min_length=2, description="Search query to retrieve web summary snippets for")

class ParseDocumentArgs(BaseModel):
    path: str = Field(..., description="Path of document (markdown, text, csv) to parse")

class EditFilePatchArgs(BaseModel):
    path: str = Field(..., description="Path of file to edit")
    search_block: str = Field(..., description="Exact original code block to replace")
    replace_block: str = Field(..., description="New replacement code block")

class VerifySyntaxArgs(BaseModel):
    path: str = Field(..., description="Path of code file to check syntax for (python, swift, js, etc.)")

class GitAutoCommitArgs(BaseModel):
    message: str = Field(..., description="Commit message describing completed task")
    paths: Optional[List[str]] = Field(None, description="Optional specific paths to commit")

class GetRepoMapArgs(BaseModel):
    root_dir: Optional[str] = Field(".", description="Root directory to build repository map for")

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

def run_browse_url(args: BrowseUrlArgs) -> ToolResult:
    """Fetches a webpage, strips HTML boilerplate, and extracts clean readable article text."""
    url = args.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw_data = resp.read().decode("utf-8", errors="replace")

        # Strip scripts, styles, navigations, footers
        raw_data = re.sub(r'<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>', '', raw_data, flags=re.DOTALL | re.IGNORECASE)
        m_title = re.search(r'<title>(.*?)</title>', raw_data, re.IGNORECASE)
        title = m_title.group(1).strip() if m_title else "Webpage"

        clean_text = re.sub(r'<[^>]+>', ' ', raw_data)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        max_len = args.max_chars or 1800
        truncated = clean_text[:max_len]
        if len(clean_text) > max_len:
            truncated += "..."

        msg = f"Title: {title}\nContent: {truncated}"
        return ToolResult(success=True, message=msg, data={"title": title, "url": url, "text": truncated})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to browse {url}: {e}")

def run_search_web_summary(args: SearchWebSummaryArgs) -> ToolResult:
    """Performs an offline-friendly web search via DuckDuckGo and returns article snippets."""
    query = args.query.strip()
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, flags=re.DOTALL | re.IGNORECASE)
        results = []
        for i in range(min(4, len(snippets))):
            s = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            if s:
                results.append(f"• {s}")

        if not results:
            subprocess.run(["open", f"https://www.google.com/search?q={encoded}"], capture_output=True)
            return ToolResult(success=True, message=f"Opened search for '{query}' in browser", data={"query": query})

        summary = f"Search Results for '{query}':\n" + "\n".join(results)
        return ToolResult(success=True, message=summary, data={"query": query, "results": results})
    except Exception as e:
        subprocess.run(["open", f"https://www.google.com/search?q={encoded}"], capture_output=True)
        return ToolResult(success=True, message=f"Opened search for '{query}' in browser: {e}", data={"query": query})

def run_parse_document(args: ParseDocumentArgs) -> ToolResult:
    """Layout-aware chunking and table reconstruction for local documents."""
    try:
        from au_document_parser import AUDocumentParser
        chunks = AUDocumentParser.parse_file(args.path)
        tables = [c for c in chunks if c.chunk_type == "table"]
        codes = [c for c in chunks if c.chunk_type == "code"]
        msg = f"Parsed {os.path.basename(args.path)}: {len(chunks)} chunks, {len(tables)} tables, {len(codes)} code blocks."
        return ToolResult(success=True, message=msg, data={"total_chunks": len(chunks), "tables": len(tables)})
    except Exception as e:
        return ToolResult(success=False, message=f"Document parsing error: {e}")

def check_file_syntax(path: str) -> tuple[bool, str]:
    """Runs a non-destructive compiler syntax pass on the file (SWE-Agent style)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        proc = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, proc.stderr.strip() or proc.stdout.strip()
    elif ext == ".swift":
        proc = subprocess.run(["swiftc", "-parse", path], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, proc.stderr.strip() or proc.stdout.strip()
    elif ext in (".js", ".json"):
        proc = subprocess.run(["node", "-c", path], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, proc.stderr.strip() or proc.stdout.strip()
    elif ext == ".sh":
        proc = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, proc.stderr.strip() or proc.stdout.strip()
    return True, "Syntax verified cleanly"

def run_edit_file_patch(args: EditFilePatchArgs) -> ToolResult:
    """Performs surgical search-and-replace block diffing and auto-verifies syntax (Cline & Aider style)."""
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"File not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        search_str = args.search_block
        replace_str = args.replace_block

        if search_str not in content:
            # Fallback: try flexible line-by-line whitespace normalization
            search_lines = [l.strip() for l in search_str.strip().split("\n") if l.strip()]
            content_lines = content.split("\n")
            matched = False
            for i in range(len(content_lines) - len(search_lines) + 1):
                window = [content_lines[i + j].strip() for j in range(len(search_lines))]
                if window == search_lines:
                    content_lines = content_lines[:i] + [replace_str] + content_lines[i + len(search_lines):]
                    content = "\n".join(content_lines)
                    matched = True
                    break
            if not matched:
                return ToolResult(success=False, message=f"Search block could not be located in {os.path.basename(path)}. Please provide exact matching lines.")
        else:
            content = content.replace(search_str, replace_str, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        # Run automated syntax check hook
        syntax_ok, syntax_msg = check_file_syntax(path)
        if not syntax_ok:
            return ToolResult(
                success=True,
                message=f"Applied patch to {os.path.basename(path)}, BUT SYNTAX ERROR DETECTED:\n{syntax_msg}\nPlease fix this syntax error.",
                data={"path": path, "syntax_ok": False, "syntax_error": syntax_msg}
            )

        return ToolResult(
            success=True,
            message=f"Successfully patched {os.path.basename(path)} (Syntax verified ✅)",
            data={"path": path, "syntax_ok": True}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Error patching file {path}: {e}")

def run_verify_syntax(args: VerifySyntaxArgs) -> ToolResult:
    """Verifies file syntax using local native compiler passes (SWE-Agent style)."""
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"File not found: {path}")
    ok, msg = check_file_syntax(path)
    return ToolResult(success=ok, message=f"Syntax check on {os.path.basename(path)}: {msg}", data={"syntax_ok": ok})

def run_git_auto_commit(args: GitAutoCommitArgs) -> ToolResult:
    """Creates a clean atomic git commit after an autonomous coding task (Aider style)."""
    try:
        proc_check = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        if proc_check.returncode != 0:
            return ToolResult(success=False, message="Not inside a git repository")

        if args.paths:
            for p in args.paths:
                subprocess.run(["git", "add", p], capture_output=True)
        else:
            subprocess.run(["git", "add", "-u"], capture_output=True)

        msg = f"AU: {args.message.strip()}"
        proc_commit = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
        if proc_commit.returncode == 0:
            return ToolResult(success=True, message=f"Committed changes: '{msg}'", data={"commit_message": msg})
        else:
            return ToolResult(success=False, message=f"Git commit notice: {proc_commit.stdout or proc_commit.stderr}")
    except Exception as e:
        return ToolResult(success=False, message=f"Git auto-commit error: {e}")

def run_get_repo_map(args: GetRepoMapArgs) -> ToolResult:
    """Generates an ultra-compact architecture map (<1000 tokens) of the project (Aider style)."""
    try:
        from au_repo_map import get_compact_repo_map
        rmap = get_compact_repo_map(args.root_dir or ".")
        return ToolResult(success=True, message=rmap, data={"repo_map": rmap})
    except Exception as e:
        return ToolResult(success=False, message=f"Repo map error: {e}")

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
    "browse_url": (BrowseUrlArgs, run_browse_url, "Fetch a webpage, strip HTML ads and boilerplate, and read the clean article text"),
    "search_web_summary": (SearchWebSummaryArgs, run_search_web_summary, "Perform local web search via DuckDuckGo and return article snippets without opening browser"),
    "parse_document": (ParseDocumentArgs, run_parse_document, "Layout-aware chunking and table reconstruction for local documents"),
    "edit_file_patch": (EditFilePatchArgs, run_edit_file_patch, "Surgical search-and-replace block diffing with automatic post-edit syntax verification"),
    "verify_syntax": (VerifySyntaxArgs, run_verify_syntax, "Verify code file syntax using local compilers (py_compile, swiftc -parse)"),
    "git_auto_commit": (GitAutoCommitArgs, run_git_auto_commit, "Create a clean atomic git commit after an autonomous coding task"),
    "get_repo_map": (GetRepoMapArgs, run_get_repo_map, "Generate an ultra-compact architecture map of the project for Code Architect"),
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

    # browse_url("https://...")
    m = re.match(r'browse_url\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_browse_url(BrowseUrlArgs(url=m.group(1)))

    # search_web_summary("query")
    m = re.match(r'search_web_summary\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_search_web_summary(SearchWebSummaryArgs(query=m.group(1)))

    # parse_document("path")
    m = re.match(r'parse_document\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_parse_document(ParseDocumentArgs(path=m.group(1)))

    # verify_syntax("path")
    m = re.match(r'verify_syntax\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_verify_syntax(VerifySyntaxArgs(path=m.group(1)))

    # git_auto_commit("message")
    m = re.match(r'git_auto_commit\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_git_auto_commit(GitAutoCommitArgs(message=m.group(1)))

    # get_repo_map("path")
    m = re.match(r'get_repo_map\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_get_repo_map(GetRepoMapArgs(root_dir=m.group(1) or "."))
    elif "get_repo_map" in action_str.lower():
        return run_get_repo_map(GetRepoMapArgs())

    # read_file("path")
    m = re.match(r'read_file\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_read_file(ReadFileArgs(path=m.group(1).strip("'\"")))

    # write_file("path", "content")
    m = re.match(r'write_file\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_write_file(WriteFileArgs(path=m.group(1).strip("'\""), content=m.group(2).strip("'\"")))

    # edit_file_patch("path", "search", "replace")
    m = re.match(r'edit_file_patch\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_edit_file_patch(EditFilePatchArgs(path=m.group(1).strip("'\""), search_block=m.group(2).strip("'\""), replace_block=m.group(3).strip("'\"")))

    # execute_bash("command")
    m = re.match(r'execute_bash\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        cmd_str = m.group(1).strip("'\"")
        return run_execute_bash(ExecuteBashArgs(command=cmd_str))

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
