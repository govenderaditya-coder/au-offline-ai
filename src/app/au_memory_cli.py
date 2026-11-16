#!/usr/bin/env python3
"""
AU Mem0 CLI — Command-line management for personal memory store.
Usage:
  au-memory list
  au-memory add "User loves jazz music" preference
  au-memory search "music"
  au-memory delete <id>
  au-memory clear
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import au_memory

def print_help():
    print("""
🧠 AU Personal Memory Engine (Mem0 SQLite)
------------------------------------------
Commands:
  au-memory list                 List all remembered personal facts
  au-memory search <query>       Search memories via full-text search
  au-memory add "<fact>" [cat]   Store a new personal memory
  au-memory delete <id>          Remove a specific memory by ID
  au-memory clear                Wipe all personal memories
""")

def main():
    engine = au_memory.AUMemoryEngine()
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print_help()
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "list":
        memories = engine.list_all(limit=50)
        if not memories:
            print("No personal memories stored yet.")
            return
        print(f"Stored Personal Memories ({len(memories)} total):")
        print("-" * 65)
        for m in memories:
            print(f"  [{m['id']:3d}] ({m['category']:<10})  {m['fact']}")
            print(f"        Accessed: {m['access_count']} times | Created: {m['created_at']}")
        print("-" * 65)

    elif cmd == "search":
        if len(args) < 2:
            print("Error: query required. Example: au-memory search python")
            sys.exit(1)
        query = " ".join(args[1:])
        results = engine.recall(query, limit=10)
        print(f"Search Results for '{query}' ({len(results)} matches):")
        for r in results:
            print(f"  • [{r['id']}] ({r['category']}): {r['fact']}")

    elif cmd == "add":
        if len(args) < 2:
            print("Error: fact text required. Example: au-memory add 'User loves jazz' preference")
            sys.exit(1)
        fact = args[1]
        category = args[2] if len(args) > 2 else "general"
        fid = engine.store_fact(fact, category=category)
        print(f"✅ Stored memory #{fid}: '{fact}' [{category}]")

    elif cmd == "delete":
        if len(args) < 2:
            print("Error: memory id required. Example: au-memory delete 3")
            sys.exit(1)
        try:
            mid = int(args[1])
            success = engine.delete_fact(mid)
            if success:
                print(f"✅ Deleted memory #{mid}")
            else:
                print(f"Memory #{mid} not found.")
        except ValueError:
            print("Error: ID must be an integer.")

    elif cmd == "clear":
        engine.clear_all()
        print("🧹 Cleared all stored personal memories.")

    else:
        print(f"Unknown command '{cmd}'.")
        print_help()

if __name__ == "__main__":
    main()
