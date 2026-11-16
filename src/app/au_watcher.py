#!/usr/bin/env python3
"""
AU Local Notes & Artifacts Watcher
Adapted from Khoj-style local directory synchronization.
Monitors ~/Documents/AU_Notes for new or modified markdown notes and automatically
syncs them into the Mem0 personal memory store.
"""

import os
import sys
import time
import glob
from typing import Dict, Set

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import au_memory
from au_document_parser import AUDocumentParser

NOTES_DIR = os.path.expanduser("~/Documents/AU_Notes")
CHECK_INTERVAL_SEC = 5

class AUNotesWatcher:
    def __init__(self, watch_dir: str = NOTES_DIR):
        self.watch_dir = watch_dir
        self.memory_engine = au_memory.AUMemoryEngine()
        self.file_mtimes: Dict[str, float] = {}
        os.makedirs(self.watch_dir, exist_ok=True)

    def scan_once(self) -> int:
        """Scans directory and indexes any new or modified files. Returns count of indexed files."""
        indexed_count = 0
        current_files = glob.glob(os.path.join(self.watch_dir, "*.md")) + glob.glob(os.path.join(self.watch_dir, "*.txt"))

        for fpath in current_files:
            try:
                mtime = os.path.getmtime(fpath)
                last_mtime = self.file_mtimes.get(fpath, 0)
                if mtime > last_mtime:
                    self._index_file(fpath)
                    self.file_mtimes[fpath] = mtime
                    indexed_count += 1
            except Exception as e:
                print(f"Error checking {fpath}: {e}", file=sys.stderr)

        return indexed_count

    def _index_file(self, fpath: str):
        fname = os.path.basename(fpath)
        try:
            chunks = AUDocumentParser.parse_file(fpath)
            for chunk in chunks[:3]:
                # Store first few summary chunks as episodic note memories
                preview = chunk.content[:200].replace("\n", " ").strip()
                fact = f"Note '{fname}' ({chunk.heading}): {preview}"
                self.memory_engine.store_fact(fact, category="notes", confidence=0.95)
            print(f"📄 [AU WATCHER]: Indexed '{fname}' into Mem0 memory store.", flush=True)
        except Exception as e:
            print(f"Error indexing {fname}: {e}", file=sys.stderr)

    def run_loop(self):
        print(f"👁️ [AU WATCHER]: Monitoring {self.watch_dir} for notes & artifacts...", flush=True)
        # Initial baseline scan
        self.scan_once()
        while True:
            try:
                time.sleep(CHECK_INTERVAL_SEC)
                self.scan_once()
            except KeyboardInterrupt:
                print("\nAU Watcher stopped.", flush=True)
                break

if __name__ == "__main__":
    watcher = AUNotesWatcher()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        count = watcher.scan_once()
        print(f"Scanned once. Indexed {count} notes.")
    else:
        watcher.run_loop()
