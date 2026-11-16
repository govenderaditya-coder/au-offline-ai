#!/usr/bin/env python3
"""
AU Project Repository Map Generator
Adapted from Aider's AST Tree-Sitter Codebase Mapping architecture.

Generates an ultra-compact, token-efficient architecture map (<1000 tokens)
summarizing classes, structs, and function signatures across Python, Swift, JS, and Shell files.
Uses Python's standard `ast` library and regex signature matchers with zero external dependencies.
"""

import os
import sys
import ast
import re
from typing import Dict, List, Optional

IGNORE_DIRS = {
    ".git", ".venv", ".venv-cloner", ".voice_env", "__pycache__",
    "node_modules", ".build", "podcasts", "voice_profile", "AU.app"
}

IGNORE_EXTENSIONS = {
    ".pyc", ".png", ".jpg", ".icns", ".wav", ".m4a", ".mp3",
    ".zip", ".tar", ".gz", ".db", ".sqlite", ".DS_Store"
}

class AURepoMapper:
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(os.path.expanduser(root_dir))

    def extract_python_signatures(self, file_path: str) -> List[str]:
        """Extracts class and function definitions from Python code using standard AST."""
        signatures = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=file_path)

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    meth_str = f" ({', '.join(methods[:4])})" if methods else ""
                    signatures.append(f"class {node.name}{meth_str}")
                elif isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args[:3]]
                    signatures.append(f"def {node.name}({', '.join(args)})")
        except Exception:
            pass
        return signatures

    def extract_swift_signatures(self, file_path: str) -> List[str]:
        """Extracts Swift classes, structs, enums, and functions using regex signatures."""
        signatures = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            matches = re.findall(
                r'^\s*(?:@\w+\s+)?(?:public\s+|private\s+|internal\s+)?(class|struct|enum|protocol|func)\s+([A-Za-z0-9_]+)',
                content,
                re.MULTILINE
            )
            for kind, name in matches[:10]:
                signatures.append(f"{kind} {name}")
        except Exception:
            pass
        return signatures

    def extract_shell_signatures(self, file_path: str) -> List[str]:
        """Extracts top-level shell functions from .sh files."""
        signatures = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            matches = re.findall(r'^\s*([A-Za-z0-9_\-]+)\s*\(\)\s*\{', content, re.MULTILINE)
            for name in matches[:6]:
                signatures.append(f"func {name}()")
        except Exception:
            pass
        return signatures

    def generate_map(self, max_files: int = 30) -> str:
        """Walks repository and builds concise architectural summary."""
        file_signatures: Dict[str, List[str]] = {}

        for root, dirs, files in os.walk(self.root_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in IGNORE_EXTENSIONS or fname.startswith("."):
                    continue

                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, self.root_dir)

                if ext == ".py":
                    sigs = self.extract_python_signatures(full_path)
                elif ext == ".swift":
                    sigs = self.extract_swift_signatures(full_path)
                elif ext == ".sh":
                    sigs = self.extract_shell_signatures(full_path)
                elif ext in (".md", ".json", ".txt"):
                    sigs = [f"[document {os.path.getsize(full_path)} bytes]"]
                else:
                    sigs = []

                if sigs:
                    file_signatures[rel_path] = sigs

                if len(file_signatures) >= max_files:
                    break
            if len(file_signatures) >= max_files:
                break

        lines = ["📁 AU Project Architecture Map:"]
        for fpath, sigs in sorted(file_signatures.items()):
            preview = ", ".join(sigs[:5])
            if len(sigs) > 5:
                preview += f" ... (+{len(sigs)-5} more)"
            lines.append(f"  • {fpath}: {preview}")

        return "\n".join(lines)

def get_compact_repo_map(root_dir: str = ".") -> str:
    mapper = AURepoMapper(root_dir)
    return mapper.generate_map()

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    print(get_compact_repo_map(target))
