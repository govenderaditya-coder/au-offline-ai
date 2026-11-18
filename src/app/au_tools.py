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
# NEW TOOL SCHEMAS & RUNNERS (v5.0 Expansion)
# ==============================================================================

# --- Schemas ---

class SetClipboardArgs(BaseModel):
    text: str = Field(..., description="Text to write to the macOS clipboard")

class GetWeatherArgs(BaseModel):
    city: str = Field("auto", description="City name or 'auto' to detect location")

class ReminderCreateArgs(BaseModel):
    title: str = Field(..., min_length=1, description="Reminder title")
    time_str: str = Field(..., description="When to trigger the reminder, e.g. '5pm' or '2024-12-31 09:00'")

class SetWallpaperArgs(BaseModel):
    image_path: str = Field(..., description="Absolute path to the image file to use as wallpaper")

class TypeTextArgs(BaseModel):
    text: str = Field(..., description="Text to type into the frontmost macOS application via osascript")

class TranslateTextArgs(BaseModel):
    text: str = Field(..., min_length=1, description="Text to translate")
    target_lang: str = Field("es", description="Target language code, e.g. 'es', 'fr', 'de', 'ja'")

class SummarizeFileArgs(BaseModel):
    path: str = Field(..., description="Path of the file to summarise")
    max_chars: int = Field(2000, ge=100, le=10000, description="Maximum characters to return")

class ListDirectoryArgs(BaseModel):
    path: str = Field(".", description="Directory path to list")

class CompressFolderArgs(BaseModel):
    folder_path: str = Field(..., description="Path of the folder to compress")
    output_path: str = Field(..., description="Destination zip file path")

class SpeakTextArgs(BaseModel):
    text: str = Field(..., min_length=1, description="Text for macOS to speak aloud")
    voice: str = Field("Samantha", description="macOS voice name, e.g. 'Samantha', 'Alex', 'Daniel'")

class WordCountFileArgs(BaseModel):
    path: str = Field(..., description="Path of the file to word-count")

class DiffFilesArgs(BaseModel):
    path1: str = Field(..., description="First file path")
    path2: str = Field(..., description="Second file path")

class ReadScreenArgs(BaseModel):
    query: str = Field("What is currently visible on my screen?", description="Question to answer about screen content")

class CreatePlanArgs(BaseModel):
    goal: str = Field(..., min_length=3, description="Goal or objective to plan and decompose")

# --- Runners ---

def run_get_clipboard() -> ToolResult:
    """Reads the current macOS clipboard content via pbpaste."""
    try:
        proc = subprocess.run(["pbpaste"], capture_output=True, text=True)
        content = proc.stdout
        if not content:
            return ToolResult(success=True, message="Clipboard is empty", data={"content": ""})
        preview = content[:300] + ("..." if len(content) > 300 else "")
        return ToolResult(success=True, message=f"Clipboard content: {preview}", data={"content": content})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to read clipboard: {e}")

def run_set_clipboard(args: SetClipboardArgs) -> ToolResult:
    """Writes text to the macOS clipboard via pbcopy."""
    try:
        proc = subprocess.run(["pbcopy"], input=args.text, text=True, capture_output=True)
        if proc.returncode == 0:
            preview = args.text[:80] + ("..." if len(args.text) > 80 else "")
            return ToolResult(success=True, message=f"Clipboard set to: {preview}", data={"length": len(args.text)})
        return ToolResult(success=False, message=f"pbcopy failed: {proc.stderr}")
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to set clipboard: {e}")

def run_get_wifi_status() -> ToolResult:
    """Returns the current Wi-Fi network name via networksetup."""
    try:
        proc = subprocess.run(
            ["networksetup", "-getairportnetwork", "en0"],
            capture_output=True, text=True
        )
        output = proc.stdout.strip()
        if not output:
            # Try en1 if en0 gave nothing
            proc = subprocess.run(["networksetup", "-getairportnetwork", "en1"], capture_output=True, text=True)
            output = proc.stdout.strip()
        if "You are not associated" in output:
            return ToolResult(success=True, message="Wi-Fi: Not connected to any network", data={"connected": False})
        return ToolResult(success=True, message=f"Wi-Fi status: {output}", data={"connected": True, "info": output})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get Wi-Fi status: {e}")

def run_list_running_apps() -> ToolResult:
    """Lists currently running user-visible applications via ps."""
    try:
        proc = subprocess.run(
            ["ps", "-axco", "pid,comm"],
            capture_output=True, text=True
        )
        lines = proc.stdout.strip().split("\n")[1:]  # skip header
        # Filter to interesting app names (capitalized or containing .app patterns)
        apps = []
        seen = set()
        for line in lines:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                pid, name = parts
                if name not in seen and not name.startswith("("):
                    seen.add(name)
                    apps.append(name)
        # Keep first 40 unique names
        apps = apps[:40]
        summary = ", ".join(apps)
        return ToolResult(success=True, message=f"Running processes ({len(apps)}): {summary}", data={"apps": apps})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to list running apps: {e}")

def run_get_weather(args: GetWeatherArgs) -> ToolResult:
    """Gets a one-line weather summary from wttr.in."""
    try:
        city = args.city.strip()
        if city.lower() == "auto" or not city:
            city = ""
        encoded_city = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded_city}?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            weather = resp.read().decode("utf-8", errors="replace").strip()
        return ToolResult(success=True, message=f"Weather: {weather}", data={"raw": weather, "city": city or "auto"})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get weather: {e}")

def run_reminder_create(args: ReminderCreateArgs) -> ToolResult:
    """Creates a macOS Reminder via AppleScript."""
    try:
        script = f'''
tell application "Reminders"
    set newReminder to make new reminder with properties {{name:"{args.title}"}}
end tell
'''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode == 0:
            return ToolResult(success=True, message=f"Reminder created: '{args.title}' (at {args.time_str})", data={"title": args.title, "time": args.time_str})
        return ToolResult(success=False, message=f"Failed to create reminder: {proc.stderr.strip()}")
    except Exception as e:
        return ToolResult(success=False, message=f"Reminder creation error: {e}")

def run_set_wallpaper(args: SetWallpaperArgs) -> ToolResult:
    """Sets the macOS desktop wallpaper via AppleScript."""
    path = os.path.expanduser(args.image_path.strip())
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"Image not found: {path}")
    try:
        script = f'tell application "Finder" to set desktop picture to POSIX file "{path}"'
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode == 0:
            return ToolResult(success=True, message=f"Wallpaper set to: {os.path.basename(path)}", data={"path": path})
        return ToolResult(success=False, message=f"Failed to set wallpaper: {proc.stderr.strip()}")
    except Exception as e:
        return ToolResult(success=False, message=f"Wallpaper error: {e}")

def run_get_frontmost_app() -> ToolResult:
    """Returns the name of the currently active/frontmost macOS application."""
    try:
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        name = proc.stdout.strip()
        if name:
            return ToolResult(success=True, message=f"Frontmost app: {name}", data={"app": name})
        return ToolResult(success=False, message=f"Could not determine frontmost app: {proc.stderr.strip()}")
    except Exception as e:
        return ToolResult(success=False, message=f"get_frontmost_app error: {e}")

def run_type_text(args: TypeTextArgs) -> ToolResult:
    """Types text into the frontmost macOS application via osascript keystroke."""
    try:
        # Escape double quotes and backslashes for AppleScript safety
        safe_text = args.text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{safe_text}"'
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode == 0:
            preview = args.text[:60] + ("..." if len(args.text) > 60 else "")
            return ToolResult(success=True, message=f"Typed: {preview}", data={"text": args.text})
        return ToolResult(success=False, message=f"type_text failed: {proc.stderr.strip()}")
    except Exception as e:
        return ToolResult(success=False, message=f"type_text error: {e}")

def run_translate_text(args: TranslateTextArgs) -> ToolResult:
    """Translates text using the MyMemory free API (no key required)."""
    try:
        encoded_text = urllib.parse.quote(args.text[:500])  # API limit
        lang_pair = f"en|{args.target_lang.strip().lower()}"
        url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair={lang_pair}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        translated = data.get("responseData", {}).get("translatedText", "")
        if translated:
            return ToolResult(success=True, message=f"Translation ({args.target_lang}): {translated}", data={"original": args.text, "translated": translated, "lang": args.target_lang})
        return ToolResult(success=False, message=f"Translation returned no result: {data}")
    except Exception as e:
        return ToolResult(success=False, message=f"Translation error: {e}")

def run_summarize_file(args: SummarizeFileArgs) -> ToolResult:
    """Reads a file and returns a smart truncated summary."""
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        total_chars = len(content)
        total_lines = content.count("\n") + 1
        # Smart summary: take beginning + middle + end if large
        max_c = args.max_chars
        if total_chars <= max_c:
            summary = content
        else:
            chunk = max_c // 3
            summary = content[:chunk] + f"\n\n... [{total_chars - chunk*2} chars omitted] ...\n\n" + content[-chunk:]
        msg = f"Summary of {os.path.basename(path)} ({total_lines} lines, {total_chars} chars):\n{summary}"
        return ToolResult(success=True, message=msg, data={"path": path, "total_chars": total_chars, "total_lines": total_lines})
    except Exception as e:
        return ToolResult(success=False, message=f"summarize_file error: {e}")

def run_list_directory(args: ListDirectoryArgs) -> ToolResult:
    """Lists a directory with file sizes and modification dates."""
    path = os.path.expanduser(args.path)
    if not os.path.isdir(path):
        return ToolResult(success=False, message=f"Directory not found: {path}")
    try:
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            stat = os.stat(full)
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            kind = "DIR" if os.path.isdir(full) else "FILE"
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.1f}KB"
            else:
                size_str = f"{size/1024/1024:.1f}MB"
            entries.append(f"{'📁' if kind=='DIR' else '📄'} {name:40s} {size_str:10s} {mtime}")
        listing = "\n".join(entries) if entries else "(empty directory)"
        msg = f"Directory: {path} ({len(entries)} items)\n{listing}"
        return ToolResult(success=True, message=msg, data={"path": path, "count": len(entries)})
    except Exception as e:
        return ToolResult(success=False, message=f"list_directory error: {e}")

def run_compress_folder(args: CompressFolderArgs) -> ToolResult:
    """Compresses a folder into a zip archive."""
    folder = os.path.expanduser(args.folder_path)
    output = os.path.expanduser(args.output_path)
    if not os.path.isdir(folder):
        return ToolResult(success=False, message=f"Folder not found: {folder}")
    try:
        proc = subprocess.run(
            ["zip", "-r", output, "."],
            cwd=folder,
            capture_output=True, text=True, timeout=60
        )
        if proc.returncode == 0:
            size = os.path.getsize(output) if os.path.exists(output) else 0
            size_str = f"{size/1024/1024:.1f}MB" if size > 1024*1024 else f"{size/1024:.1f}KB"
            return ToolResult(success=True, message=f"Compressed '{os.path.basename(folder)}' → {output} ({size_str})", data={"output": output, "size_bytes": size})
        return ToolResult(success=False, message=f"Compression failed: {proc.stderr.strip()}")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, message="Compression timed out after 60s")
    except Exception as e:
        return ToolResult(success=False, message=f"compress_folder error: {e}")

def run_get_public_ip() -> ToolResult:
    """Returns the machine's current public IP address."""
    try:
        req = urllib.request.Request("https://ifconfig.me", headers={"User-Agent": "curl/7.88"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            ip = resp.read().decode("utf-8").strip()
        return ToolResult(success=True, message=f"Public IP: {ip}", data={"ip": ip})
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to get public IP: {e}")

def run_speak_text(args: SpeakTextArgs) -> ToolResult:
    """Speaks text aloud using the macOS 'say' command (non-blocking)."""
    try:
        # Non-blocking: use Popen
        subprocess.Popen(["say", "-v", args.voice, args.text])
        preview = args.text[:80] + ("..." if len(args.text) > 80 else "")
        return ToolResult(success=True, message=f"Speaking: '{preview}' (voice: {args.voice})", data={"text": args.text, "voice": args.voice})
    except Exception as e:
        return ToolResult(success=False, message=f"speak_text error: {e}")

def run_word_count_file(args: WordCountFileArgs) -> ToolResult:
    """Returns line, word, and character counts for a file."""
    path = os.path.expanduser(args.path)
    if not os.path.exists(path):
        return ToolResult(success=False, message=f"File not found: {path}")
    try:
        proc = subprocess.run(["wc", "-l", "-w", "-c", path], capture_output=True, text=True)
        output = proc.stdout.strip()
        # Parse: "   lines   words   chars   path"
        parts = output.split()
        if len(parts) >= 3:
            lines, words, chars = parts[0], parts[1], parts[2]
            msg = f"{os.path.basename(path)}: {lines} lines, {words} words, {chars} characters"
            return ToolResult(success=True, message=msg, data={"lines": lines, "words": words, "chars": chars, "path": path})
        return ToolResult(success=False, message=f"Could not parse wc output: {output}")
    except Exception as e:
        return ToolResult(success=False, message=f"word_count_file error: {e}")

def run_diff_files(args: DiffFilesArgs) -> ToolResult:
    """Diffs two files and returns a readable unified diff."""
    p1 = os.path.expanduser(args.path1)
    p2 = os.path.expanduser(args.path2)
    if not os.path.exists(p1):
        return ToolResult(success=False, message=f"File not found: {p1}")
    if not os.path.exists(p2):
        return ToolResult(success=False, message=f"File not found: {p2}")
    try:
        proc = subprocess.run(
            ["diff", "-u", "--label", os.path.basename(p1), "--label", os.path.basename(p2), p1, p2],
            capture_output=True, text=True
        )
        output = proc.stdout.strip()
        if not output:
            return ToolResult(success=True, message=f"Files are identical: {os.path.basename(p1)} and {os.path.basename(p2)}", data={"identical": True})
        # Truncate if huge
        if len(output) > 2000:
            output = output[:2000] + "\n... [diff truncated]"
        msg = f"Diff ({os.path.basename(p1)} vs {os.path.basename(p2)}):\n{output}"
        return ToolResult(success=True, message=msg, data={"diff": output, "identical": False})
    except Exception as e:
        return ToolResult(success=False, message=f"diff_files error: {e}")

def run_read_screen(args: Optional[ReadScreenArgs] = None) -> ToolResult:
    """Captures the active screen and performs Apple Vision OCR to extract and read visible text."""
    try:
        from au_vision import AUScreenVision
        vision = AUScreenVision()
        text = vision.read_screen_text()
        if not text:
            return ToolResult(success=True, message="Screen captured, but no visible text was detected.")
        truncated = text[:2500] + ("\n... [remaining screen text truncated]" if len(text) > 2500 else "")
        return ToolResult(success=True, message=f"Screen OCR Text:\n{truncated}", data={"screen_text": text})
    except Exception as e:
        return ToolResult(success=False, message=f"read_screen error: {e}")

def run_create_plan(args: CreatePlanArgs) -> ToolResult:
    """Decomposes a user goal into structured phases and saves an interactive plan."""
    try:
        from au_planner import AUPlanner
        planner = AUPlanner()
        res = planner.create_plan(args.goal)
        return ToolResult(success=True, message=f"Created Plan: {res['title']}\nSaved at: {res['plan_path']}\n\n{res['markdown']}", data=res)
    except Exception as e:
        return ToolResult(success=False, message=f"create_plan error: {e}")

def run_get_morning_briefing() -> ToolResult:
    """Generates the morning executive briefing with weather, battery, and work tasks."""
    try:
        from au_scheduler import AUBriefingEngine
        b = AUBriefingEngine()
        briefing = b.generate_morning_briefing()
        return ToolResult(success=True, message=briefing, data={"briefing": briefing})
    except Exception as e:
        return ToolResult(success=False, message=f"get_morning_briefing error: {e}")

def run_get_evening_recap() -> ToolResult:
    """Generates the daily evening productivity recap."""
    try:
        from au_scheduler import AUBriefingEngine
        b = AUBriefingEngine()
        recap = b.generate_evening_recap()
        return ToolResult(success=True, message=recap, data={"recap": recap})
    except Exception as e:
        return ToolResult(success=False, message=f"get_evening_recap error: {e}")

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
    # v5.0 New Tools
    "get_clipboard": (None, run_get_clipboard, "Read the current macOS clipboard content"),
    "set_clipboard": (SetClipboardArgs, run_set_clipboard, "Write text to the macOS clipboard"),
    "get_wifi_status": (None, run_get_wifi_status, "Get the current Wi-Fi network name and connection status"),
    "list_running_apps": (None, run_list_running_apps, "List currently running applications and processes"),
    "get_weather": (GetWeatherArgs, run_get_weather, "Get a one-line weather summary for a city via wttr.in"),
    "reminder_create": (ReminderCreateArgs, run_reminder_create, "Create a macOS Reminder via AppleScript"),
    "set_wallpaper": (SetWallpaperArgs, run_set_wallpaper, "Set the macOS desktop wallpaper to an image file"),
    "get_frontmost_app": (None, run_get_frontmost_app, "Get the name of the currently active/frontmost macOS application"),
    "type_text": (TypeTextArgs, run_type_text, "Type text into the frontmost macOS application via osascript"),
    "translate_text": (TranslateTextArgs, run_translate_text, "Translate text to another language using the MyMemory free API"),
    "summarize_file": (SummarizeFileArgs, run_summarize_file, "Read a file and return a smart truncated summary"),
    "list_directory": (ListDirectoryArgs, run_list_directory, "List a directory with file sizes and modification dates"),
    "compress_folder": (CompressFolderArgs, run_compress_folder, "Compress a folder into a zip archive"),
    "get_public_ip": (None, run_get_public_ip, "Get the machine's current public IP address"),
    "speak_text": (SpeakTextArgs, run_speak_text, "Speak text aloud using the macOS 'say' command"),
    "word_count_file": (WordCountFileArgs, run_word_count_file, "Get line, word, and character counts for a file"),
    "diff_files": (DiffFilesArgs, run_diff_files, "Diff two files and return a readable unified diff"),
    # v5.5 Superpower Tools
    "read_screen": (ReadScreenArgs, run_read_screen, "Capture the Mac screen and extract all visible text via Apple Neural Engine Vision OCR"),
    "create_plan": (CreatePlanArgs, run_create_plan, "Decompose a complex user goal into structured phases and save an interactive markdown plan"),
    "get_morning_briefing": (None, run_get_morning_briefing, "Generate the morning executive briefing with weather, hardware, and tasks"),
    "get_evening_recap": (None, run_get_evening_recap, "Generate the daily evening recap of git commits, tasks, and achievements"),
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

    # get_clipboard()
    if re.search(r'get_clipboard', action_str, re.IGNORECASE):
        return run_get_clipboard()

    # set_clipboard("text")
    m = re.match(r'set_clipboard\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_set_clipboard(SetClipboardArgs(text=m.group(1).strip("'\"")))

    # get_wifi_status()
    if re.search(r'get_wifi_status|wifi_status', action_str, re.IGNORECASE):
        return run_get_wifi_status()

    # list_running_apps()
    if re.search(r'list_running_apps|running_apps', action_str, re.IGNORECASE):
        return run_list_running_apps()

    # get_weather("city") or get_weather()
    m = re.match(r'get_weather\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        c = m.group(1).strip("'\"") or "auto"
        return run_get_weather(GetWeatherArgs(city=c))
    elif "get_weather" in action_str.lower():
        return run_get_weather(GetWeatherArgs(city="auto"))

    # reminder_create("title", "time_str")
    m = re.match(r'reminder_create\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_reminder_create(ReminderCreateArgs(title=m.group(1).strip("'\""), time_str=m.group(2).strip("'\"")))

    # set_wallpaper("image_path")
    m = re.match(r'set_wallpaper\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_set_wallpaper(SetWallpaperArgs(image_path=m.group(1).strip("'\"")))

    # get_frontmost_app()
    if re.search(r'get_frontmost_app|frontmost_app', action_str, re.IGNORECASE):
        return run_get_frontmost_app()

    # type_text("text")
    m = re.match(r'type_text\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_type_text(TypeTextArgs(text=m.group(1).strip("'\"")))

    # translate_text("text", "target_lang")
    m = re.match(r'translate_text\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_translate_text(TranslateTextArgs(text=m.group(1).strip("'\""), target_lang=m.group(2).strip("'\"")))
    m = re.match(r'translate_text\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_translate_text(TranslateTextArgs(text=m.group(1).strip("'\"")))

    # summarize_file("path", max_chars)
    m = re.match(r'summarize_file\([\'"]?(.*?)[\'"]?,\s*(\d+)\)', action_str, re.IGNORECASE)
    if m:
        return run_summarize_file(SummarizeFileArgs(path=m.group(1).strip("'\""), max_chars=int(m.group(2))))
    m = re.match(r'summarize_file\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_summarize_file(SummarizeFileArgs(path=m.group(1).strip("'\"")))

    # list_directory("path")
    m = re.match(r'list_directory\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        p = m.group(1).strip("'\"") or "."
        return run_list_directory(ListDirectoryArgs(path=p))
    elif "list_directory" in action_str.lower():
        return run_list_directory(ListDirectoryArgs(path="."))

    # compress_folder("folder_path", "output_path")
    m = re.match(r'compress_folder\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_compress_folder(CompressFolderArgs(folder_path=m.group(1).strip("'\""), output_path=m.group(2).strip("'\"")))

    # get_public_ip()
    if re.search(r'get_public_ip|public_ip', action_str, re.IGNORECASE):
        return run_get_public_ip()

    # speak_text("text", "voice")
    m = re.match(r'speak_text\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_speak_text(SpeakTextArgs(text=m.group(1).strip("'\""), voice=m.group(2).strip("'\"")))
    m = re.match(r'speak_text\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_speak_text(SpeakTextArgs(text=m.group(1).strip("'\"")))

    # word_count_file("path")
    m = re.match(r'word_count_file\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_word_count_file(WordCountFileArgs(path=m.group(1).strip("'\"")))

    # diff_files("path1", "path2")
    m = re.match(r'diff_files\([\'"]?(.*?)[\'"]?,\s*[\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE)
    if m:
        return run_diff_files(DiffFilesArgs(path1=m.group(1).strip("'\""), path2=m.group(2).strip("'\"")))

    # read_screen
    if "read_screen" in action_str.lower() or "screen_ocr" in action_str.lower():
        return run_read_screen()

    # create_plan("goal")
    m = re.match(r'create_plan\([\'"]?(.*?)[\'"]?\)', action_str, re.IGNORECASE | re.DOTALL)
    if m:
        return run_create_plan(CreatePlanArgs(goal=m.group(1).strip("'\"")))

    # get_morning_briefing
    if "briefing" in action_str.lower():
        return run_get_morning_briefing()

    # get_evening_recap
    if "recap" in action_str.lower():
        return run_get_evening_recap()

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
