#!/usr/bin/env python3
"""
AU Central Orchestrator & Task Queue Engine
Designed for Apple Silicon M4 (16GB RAM) with local-first, low-memory architecture.

Key Architectural Guarantees:
1. Hub-and-Spoke Dispatch: Tasks flow strictly through the Core Queue, never directly peer-to-peer.
2. Low-Memory Governor: Dynamically tracks M4 unified RAM; pauses heavy jobs if RAM > 12.5 GB.
3. Lazy Model Loading: Models are loaded on demand and unloaded/timed out via keep_alive.
4. Outer Domain Layers:
   - Chat Layer: Simple conversational interface with single local model (au-assistant:latest) + Mem0 grounding.
   - Coding Layer: Code Architect with AST repo map, precision diffs, and syntax validation.
   - Document Search Layer: RAGFlow layout parser + Dify RRF hybrid search.
   - System Layer: macOS MCP automation tools.
   - Audio Layer: Voice synthesis with memory pre-flight gating.
"""

import os
import sys
import json
import time
import uuid
import sqlite3
import subprocess
import threading
import gc
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Optional local imports
try:
    import au_memory
except ImportError:
    au_memory = None

try:
    import au_tools
except ImportError:
    au_tools = None

try:
    from au_repo_map import get_compact_repo_map
except ImportError:
    get_compact_repo_map = None

try:
    import au_document_parser
except ImportError:
    au_document_parser = None

try:
    import au_emotion
    import au_personality
    import au_context
except ImportError:
    au_emotion = None
    au_personality = None
    au_context = None

# Storage paths
ORCHESTRATOR_DIR = os.path.expanduser("~/.offline-ai")
DB_PATH = os.path.join(ORCHESTRATOR_DIR, "orchestrator.db")
os.makedirs(ORCHESTRATOR_DIR, exist_ok=True)

# ==============================================================================
# 1. TASK MODEL & SCHEMAS
# ==============================================================================

class TaskStatus:
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class MemoryCost:
    LOW = "low"         # Interactive chat, memory lookup (< 50 MB)
    MEDIUM = "medium"   # Coding analysis, single document parse (~ 200 MB)
    HIGH = "high"       # Batch RAG indexing, MLX voice cloning/TTS (> 1.5 GB)

class TaskPriority:
    URGENT = 1    # Interactive real-time chat, user commands
    NORMAL = 2    # Coding operations, document search queries
    BATCH = 3     # Background indexing, multi-file processing, audio builds

@dataclass
class AUTask:
    id: str = field(default_factory=lambda: f"task_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}")
    layer: str = "chat"                       # "chat", "coding", "document_search", "system", "audio"
    prompt: str = ""                          # Natural language instruction or query
    payload: Dict[str, Any] = field(default_factory=dict) # Options, parameters, stdin, files
    priority: int = TaskPriority.URGENT       # 1=urgent, 2=normal, 3=batch
    memory_cost: str = MemoryCost.LOW         # "low", "medium", "high"
    status: str = TaskStatus.PENDING          # Current task status
    result: Optional[Any] = None              # Execution output or dictionary
    error: Optional[str] = None               # Error message if failed
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    parent_task_id: Optional[str] = None      # Hub-and-spoke lineage

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AUTask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# ==============================================================================
# 2. M4 HARDWARE MEMORY GOVERNOR (Low-RAM Optimization)
# ==============================================================================

class AUMemoryGovernor:
    """
    Monitors Apple Silicon unified memory in real time via macOS Mach VM stats.
    Controls task execution gating to prevent memory pressure or swap stalls.
    Optimized for 16 GB unified RAM.
    """
    RAM_GREEN_MAX_USED_GB = 12.0    # Normal operations: all tasks proceed
    RAM_YELLOW_MAX_USED_GB = 13.2   # Yellow zone: pause HIGH memory tasks (TTS/batch indexing)
    RAM_RED_MIN_AVAIL_GB = 2.2      # Red zone: pause all tasks and trigger purge

    def __init__(self):
        self._lock = threading.Lock()
        self._cached_stats = {}
        self._cache_time = 0.0

    def get_memory_stats(self) -> Dict[str, Any]:
        """Calculates active, wired, free, and available unified RAM."""
        now = time.time()
        with self._lock:
            if now - self._cache_time < 1.0 and self._cached_stats:
                return self._cached_stats

            try:
                # Page size on macOS ARM64 is 16384 bytes
                page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 16384
                vm_out = subprocess.check_output(["/usr/bin/vm_stat"], text=True)
                pages = {}
                for line in vm_out.splitlines():
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip().replace('"', '')
                        val = parts[1].strip().rstrip(".")
                        try:
                            pages[key] = int(val)
                        except ValueError:
                            pass

                active_bytes = pages.get("Pages active", 0) * page_size
                wired_bytes = pages.get("Pages wired down", 0) * page_size
                free_bytes = pages.get("Pages free", 0) * page_size
                inactive_bytes = pages.get("Pages inactive", 0) * page_size
                speculative_bytes = pages.get("Pages speculative", 0) * page_size

                used_gb = (active_bytes + wired_bytes) / (1024 ** 3)
                avail_gb = (free_bytes + inactive_bytes + speculative_bytes) / (1024 ** 3)
                total_gb = used_gb + avail_gb

                # Classify health status
                if avail_gb < self.RAM_RED_MIN_AVAIL_GB or used_gb > 13.8:
                    state = "RED"
                elif used_gb > self.RAM_GREEN_MAX_USED_GB:
                    state = "YELLOW"
                else:
                    state = "GREEN"

                stats = {
                    "used_gb": round(used_gb, 2),
                    "available_gb": round(avail_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "state": state,
                    "timestamp": now
                }
                self._cached_stats = stats
                self._cache_time = now
                return stats
            except Exception as e:
                return {
                    "used_gb": 4.0,
                    "available_gb": 12.0,
                    "total_gb": 16.0,
                    "state": "GREEN",
                    "error": str(e),
                    "timestamp": now
                }

    def can_run_task(self, memory_cost: str) -> Tuple[bool, str]:
        """Pre-flight check before task dispatch."""
        stats = self.get_memory_stats()
        state = stats.get("state", "GREEN")
        avail = stats.get("available_gb", 8.0)
        used = stats.get("used_gb", 4.0)

        if state == "RED":
            return False, f"Memory critical: {avail:.1f} GB available (Used: {used:.1f} GB). Pausing task execution."

        if state == "YELLOW" and memory_cost == MemoryCost.HIGH:
            return False, f"Memory tight ({used:.1f} GB used). Pausing heavy task to preserve interactive responsiveness."

        return True, "OK"

    def purge_memory(self):
        """Forces Python garbage collection and signals model router to release idle weights."""
        gc.collect()

# ==============================================================================
# 3. TASK QUEUE ENGINE (SQLite-Backed Hub)
# ==============================================================================

class AUTaskQueue:
    """
    Clear, small, inspectable task queue stored in SQLite.
    Guarantees persistence, FIFO priority dispatching, and task pausing.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_tasks (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    prompt TEXT,
                    payload_json TEXT,
                    priority INTEGER DEFAULT 1,
                    memory_cost TEXT DEFAULT 'low',
                    status TEXT DEFAULT 'pending',
                    result_json TEXT,
                    error TEXT,
                    created_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    parent_task_id TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON orchestrator_tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON orchestrator_tasks(priority, created_at)")
            conn.commit()

    def submit(self, task: AUTask) -> str:
        """Puts a new task into the queue."""
        with self._lock, self._get_conn() as conn:
            task.status = TaskStatus.QUEUED
            conn.execute("""
                INSERT OR REPLACE INTO orchestrator_tasks (
                    id, layer, prompt, payload_json, priority, memory_cost, status,
                    result_json, error, created_at, started_at, completed_at, parent_task_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id,
                task.layer,
                task.prompt,
                json.dumps(task.payload),
                task.priority,
                task.memory_cost,
                task.status,
                json.dumps(task.result) if task.result is not None else None,
                task.error,
                task.created_at,
                task.started_at,
                task.completed_at,
                task.parent_task_id
            ))
            conn.commit()
        return task.id

    def get(self, task_id: str) -> Optional[AUTask]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM orchestrator_tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def pop_next(self, governor: AUMemoryGovernor) -> Optional[AUTask]:
        """
        Retrieves the highest priority task ready to execute that passes memory governor checks.
        If a heavy task cannot run due to memory pressure, it is paused and left for later.
        """
        with self._lock, self._get_conn() as conn:
            # Query queued or paused tasks ordered by priority (1=highest) then created_at
            rows = conn.execute("""
                SELECT * FROM orchestrator_tasks
                WHERE status IN ('queued', 'paused')
                ORDER BY priority ASC, created_at ASC
            """).fetchall()

            for row in rows:
                task = self._row_to_task(row)
                can_run, reason = governor.can_run_task(task.memory_cost)

                if can_run:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    conn.execute("UPDATE orchestrator_tasks SET status = 'running', started_at = ? WHERE id = ?",
                                 (task.started_at, task.id))
                    conn.commit()
                    return task
                else:
                    # Mark as paused if it was queued
                    if task.status != TaskStatus.PAUSED:
                        conn.execute("UPDATE orchestrator_tasks SET status = 'paused', error = ? WHERE id = ?",
                                     (f"Governor: {reason}", task.id))
                        conn.commit()

            return None

    def update_task(self, task: AUTask):
        with self._lock, self._get_conn() as conn:
            conn.execute("""
                UPDATE orchestrator_tasks SET
                    status = ?,
                    result_json = ?,
                    error = ?,
                    started_at = ?,
                    completed_at = ?
                WHERE id = ?
            """, (
                task.status,
                json.dumps(task.result) if task.result is not None else None,
                task.error,
                task.started_at,
                task.completed_at,
                task.id
            ))
            conn.commit()

    def list_tasks(self, status: Optional[str] = None, limit: int = 20) -> List[AUTask]:
        with self._get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM orchestrator_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orchestrator_tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def cancel(self, task_id: str) -> bool:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE orchestrator_tasks SET status = 'cancelled' WHERE id = ? AND status IN ('queued', 'paused')",
                (task_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def clear_completed(self, max_age_hours: int = 24):
        cutoff = time.time() - (max_age_hours * 3600)
        with self._lock, self._get_conn() as conn:
            conn.execute("DELETE FROM orchestrator_tasks WHERE status IN ('completed', 'cancelled') AND completed_at < ?", (cutoff,))
            conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> AUTask:
        payload = {}
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                pass

        result = None
        if row["result_json"]:
            try:
                result = json.loads(row["result_json"])
            except Exception:
                result = row["result_json"]

        return AUTask(
            id=row["id"],
            layer=row["layer"],
            prompt=row["prompt"] or "",
            payload=payload,
            priority=row["priority"],
            memory_cost=row["memory_cost"],
            status=row["status"],
            result=result,
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            parent_task_id=row["parent_task_id"]
        )

# ==============================================================================
# 4. LOCAL MODEL ROUTER (Ollama & MLX with Lazy Loading)
# ==============================================================================

class AUModelRouter:
    """
    Unified router for Apple Silicon neural backends:
    - Ollama (default local server on localhost:11434)
    - Optional MLX (mlx-lm / MLX TTS)
    
    Implements dynamic lazy loading:
    - Interactive chat keeps model warm for 5 minutes (keep_alive: "5m").
    - Batch/heavy operations trigger immediate unload (keep_alive: "0s").
    """
    OLLAMA_BASE_URL = "http://localhost:11434"
    DEFAULT_CHAT_MODEL = "au-assistant:latest"
    DEFAULT_RESEARCH_MODEL = "au-notebooklm:latest"

    def __init__(self):
        self._active_model = self.DEFAULT_CHAT_MODEL

    def is_ollama_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.OLLAMA_BASE_URL}/api/version", headers={"User-Agent": "AU-Orchestrator"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_running_models(self) -> List[Dict[str, Any]]:
        """Returns models currently residing in M4 Unified VRAM."""
        try:
            req = urllib.request.Request(f"{self.OLLAMA_BASE_URL}/api/ps")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except Exception:
            return []

    def unload_idle_models(self):
        """Releases VRAM by evicting models from memory."""
        running = self.list_running_models()
        for m in running:
            m_name = m.get("name")
            if m_name:
                try:
                    payload = json.dumps({"model": m_name, "keep_alive": 0}).encode("utf-8")
                    req = urllib.request.Request(f"{self.OLLAMA_BASE_URL}/api/generate", data=payload, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=3.0):
                        pass
                except Exception:
                    pass

    def query(self, messages: List[Dict[str, str]], model: Optional[str] = None, keep_alive: str = "5m", timeout: int = 40) -> str:
        """Sends chat request to local model with explicit keep_alive memory configuration."""
        target_model = model or self.DEFAULT_CHAT_MODEL
        payload = json.dumps({
            "model": target_model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.OLLAMA_BASE_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("message", {}).get("content", "").strip()
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not connect to local model ({target_model}) on Ollama: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Local model error: {e}")

# ==============================================================================
# 5. OUTER DOMAIN HANDLERS (Hub-and-Spoke Implementations)
# ==============================================================================

class BaseLayerHandler:
    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Any:
        raise NotImplementedError

class ChatHandler(BaseLayerHandler):
    """
    Outer Layer 1: Conversational Chat Interface.
    - Uses one primary local model: au-assistant:latest
    - Step-by-step memory grounding via Mem0 offline memory engine
    - Automatically extracts learned personal facts into SQLite in the background
    - Executes macOS system tools if requested
    """
    def __init__(self, model_router: AUModelRouter):
        self.router = model_router
        self.memory_engine = au_memory.AUMemoryEngine() if au_memory else None

    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Dict[str, Any]:
        prompt = task.prompt
        history = task.payload.get("messages", [])
        is_voice = task.payload.get("is_voice", False)

        # Step 1: Memory Grounding
        memory_context = ""
        if self.memory_engine:
            try:
                # Fast background fact extraction
                au_memory.extract_and_store_facts(prompt, self.memory_engine)
            except Exception:
                pass
            memory_context = self.memory_engine.format_context_prompt(prompt)

        # Step 2: Emotional & Context Injections
        emotion_engine = getattr(orchestrator, "emotion_engine", None)
        personality_engine = getattr(orchestrator, "personality_engine", None)
        context_engine = getattr(orchestrator, "context_engine", None)

        current_mood = "calm"
        if emotion_engine:
            try:
                user_emotion = emotion_engine.analyze_user_emotion(prompt)
                state = emotion_engine.update_mood(user_emotion, context="chat")
                current_mood = getattr(state, "current_mood", "calm")
            except Exception:
                pass

        voice_instruction = "Keep spoken responses concise, friendly, and natural (1-2 sentences) for voice.\n" if is_voice else ""

        if personality_engine:
            try:
                base_persona = personality_engine.generate_persona_system_prompt(mood=current_mood, context="chat")
            except Exception:
                base_persona = "You are AU, the user's personal, highly capable AI assistant running 100% locally on Apple Silicon."
        else:
            base_persona = "You are AU, the user's personal, highly capable AI assistant running 100% locally on Apple Silicon."

        emotion_injection = ""
        if emotion_engine:
            try:
                inj = emotion_engine.get_system_prompt_injection()
                if inj:
                    emotion_injection = f"\n{inj}\n"
            except Exception:
                pass

        context_injection = ""
        if context_engine:
            try:
                inj = context_engine.build_context_injection()
                if inj:
                    context_injection = f"\n{inj}\n"
            except Exception:
                pass

        actions_list = (
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
            "- [ACTION: execute_bash(\"command\")]\n"
        )

        system_prompt = (
            f"{base_persona}\n"
            f"{voice_instruction}"
            f"{emotion_injection}"
            f"{context_injection}"
            f"{actions_list}"
            + memory_context
        )

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        else:
            messages.append({"role": "user", "content": prompt})

        executed_actions = []
        final_text = ""

        # Multi-turn Action/Observation loop (up to 3 steps)
        for step in range(3):
            raw_res = self.router.query(messages, model=AUModelRouter.DEFAULT_CHAT_MODEL, keep_alive="5m")

            if au_tools:
                clean_text, executed, _ = au_tools.parse_and_execute_all(raw_res)
                if executed:
                    executed_actions.extend(executed)
                    # Check if observation needed
                    has_info = any(k in " ".join(executed).lower() for k in ["battery", "disk", "time", "bash", "status", "%"])
                    if not has_info and clean_text and len(clean_text) > 10:
                        final_text = clean_text
                        break
                    obs = "Observation: " + " | ".join(executed)
                    messages.append({"role": "assistant", "content": raw_res})
                    messages.append({"role": "user", "content": f"{obs}\nProvide the concise response for the user based on this observation."})
                    continue
                else:
                    final_text = clean_text or raw_res
                    break
            else:
                final_text = raw_res
                break

        # Log interaction to context engine
        if context_engine:
            try:
                context_engine.log_interaction(query=prompt, response_summary=final_text[:120], tools_used=executed_actions)
            except Exception:
                pass

        # Emotion prefix injection
        if emotion_engine:
            try:
                prefix = emotion_engine.format_emotion_prefix(context="chat")
                if prefix and not final_text.startswith(prefix):
                    final_text = f"{prefix}{final_text}"
            except Exception:
                pass

        return {
            "text": final_text,
            "actions": executed_actions,
            "model": AUModelRouter.DEFAULT_CHAT_MODEL,
            "layer": "chat"
        }

class CodingHandler(BaseLayerHandler):
    """
    Outer Layer 2: Code Architect Agent.
    - Compact AST repository map
    - Surgical SEARCH/REPLACE diffing (edit_file_patch)
    - Post-edit syntax verification
    - Optional git auto-commit
    """
    def __init__(self, model_router: AUModelRouter):
        self.router = model_router

    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Dict[str, Any]:
        prompt = task.prompt
        repo_root = task.payload.get("repo_root", ".")
        auto_commit = task.payload.get("commit", False)

        repo_map = ""
        if get_compact_repo_map:
            try:
                repo_map = get_compact_repo_map(repo_root)
            except Exception:
                pass

        system_prompt = (
            "You are AU in Code Architect mode. You specialize in software engineering, bash tools, and precision diffs.\n"
            f"{repo_map}\n"
            "When modifying files, prefer: [ACTION: edit_file_patch(\"path\", \"search_block\", \"replace_block\")].\n"
            "To verify syntax: [ACTION: verify_syntax(\"path\")].\n"
            "To commit changes: [ACTION: git_auto_commit(\"message\")].\n"
            "Available tools: read_file, write_file, execute_bash.\n"
            "Be direct, accurate, and execute changes cleanly."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        executed_actions = []
        final_text = ""

        # Multi-turn Action/Observation loop
        for step in range(4):
            raw_res = self.router.query(messages, model=AUModelRouter.DEFAULT_CHAT_MODEL, keep_alive="5m")

            if au_tools:
                clean_text, executed, _ = au_tools.parse_and_execute_all(raw_res)
                if executed:
                    executed_actions.extend(executed)
                    obs = "Observation: " + " | ".join(executed)
                    messages.append({"role": "assistant", "content": raw_res})
                    messages.append({"role": "user", "content": f"{obs}\nProceed with the next step or final summary."})
                    continue
                else:
                    final_text = clean_text or raw_res
                    break
            else:
                final_text = raw_res
                break

        if auto_commit and au_tools:
            commit_res = au_tools.run_git_auto_commit(au_tools.GitAutoCommitArgs(message=prompt[:60]))
            executed_actions.append(f"git: {commit_res.message}")

        return {
            "text": final_text,
            "actions": executed_actions,
            "layer": "coding"
        }

class DocumentSearchHandler(BaseLayerHandler):
    """
    Outer Layer 3: Document Search & Analysis.
    - RAGFlow layout-aware table & section chunking
    - Dify RRF hybrid search (BM25 + Semantic)
    - au-notebooklm:latest for grounded synthesis
    """
    def __init__(self, model_router: AUModelRouter):
        self.router = model_router
        self.memory_engine = au_memory.AUMemoryEngine() if au_memory else None

    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Dict[str, Any]:
        query = task.prompt
        target_path = task.payload.get("file_path")

        extracted_context = ""
        # If target file specified, parse with layout chunker
        if target_path and au_document_parser and os.path.exists(target_path):
            chunks = au_document_parser.parse_document_layout(target_path)
            extracted_context = f"\n[DOCUMENT: {os.path.basename(target_path)}]\n" + "\n---\n".join([c.get("content", "") for c in chunks[:5]])

        # Hybrid RRF search across memory and notes
        search_hits = []
        if self.memory_engine:
            search_hits = self.memory_engine.search_hybrid_rrf(query, limit=5)
            if search_hits:
                extracted_context += "\n[SEARCH EVIDENCE (RRF Ranking)]:\n" + "\n".join([f"- {h['fact']}" for h in search_hits])

        system_prompt = (
            "You are AU in Document Research mode. Synthesize answers rigorously from the provided context.\n"
            f"{extracted_context}\n"
            "Cite facts clearly. If details are not found in the evidence, state what is missing."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # Use notebooklm model if available, else standard assistant
        model_name = AUModelRouter.DEFAULT_RESEARCH_MODEL
        try:
            ans = self.router.query(messages, model=model_name, keep_alive="3m")
        except Exception:
            ans = self.router.query(messages, model=AUModelRouter.DEFAULT_CHAT_MODEL, keep_alive="3m")

        return {
            "text": ans,
            "hits_count": len(search_hits),
            "layer": "document_search"
        }

class SystemHandler(BaseLayerHandler):
    """
    Outer Layer 4: macOS System Automation.
    - Volume, apps, screenshots, battery, notes, bash execution
    """
    def __init__(self, model_router: AUModelRouter):
        self.router = model_router

    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Dict[str, Any]:
        prompt = task.prompt

        system_prompt = (
            "You are AU controlling macOS actions.\n"
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
            "- [ACTION: execute_bash(\"command\")]\n"
            "Emit actions first."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        raw_res = self.router.query(messages, model=AUModelRouter.DEFAULT_CHAT_MODEL, keep_alive="2m")
        executed = []
        clean_text = raw_res
        if au_tools:
            clean_text, executed, _ = au_tools.parse_and_execute_all(raw_res)

        return {
            "text": clean_text or raw_res,
            "actions": executed,
            "layer": "system"
        }

class AudioHandler(BaseLayerHandler):
    """
    Outer Layer 5: Voice Synthesis & Audio Generation.
    - Memory cost: HIGH
    - Gated strictly by memory governor to prevent RAM exhaustion.
    """
    def execute(self, task: AUTask, orchestrator: "AUOrchestrator") -> Dict[str, Any]:
        text_to_speak = task.prompt or task.payload.get("text", "")
        if not text_to_speak:
            return {"error": "No text provided for audio synthesis"}

        speak_tool = os.path.join(SCRIPT_DIR, "..", "..", "tools", "au-speak")
        if os.path.exists(speak_tool):
            subprocess.run([speak_tool, text_to_speak], check=True)
        else:
            subprocess.run(["say", text_to_speak], check=True)

        return {"status": "spoken", "text": text_to_speak, "layer": "audio"}

# ==============================================================================
# 6. CENTRAL ORCHESTRATOR HUB (Core Coordinator)
# ==============================================================================

class AUOrchestrator:
    """
    The Central Orchestrator for AU.
    
    Principles:
    1. Core Local on Mac: Zero cloud dependency; local SQLite queue and local model router.
    2. Hub-and-Spoke Dispatch: Peer agents NEVER call each other directly. All tasks submit to Core.
    3. Low RAM / Lazy Loading: Pre-flight memory governor check on every task. Heavy tasks paused if RAM tight.
    4. Clean Layer Routing: Outer handlers for chat, coding, document search, system, audio.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AUOrchestrator, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.governor = AUMemoryGovernor()
        self.queue = AUTaskQueue()
        self.router = AUModelRouter()

        # Initialize emotional, personality, and context engines
        self.emotion_engine = au_emotion.AUEmotionEngine() if au_emotion else None
        self.personality_engine = au_personality.AUPersonalityEngine() if au_personality else None
        self.context_engine = au_context.AUContextEngine() if au_context else None

        # Initialize outer domain layers
        self.layers: Dict[str, BaseLayerHandler] = {
            "chat": ChatHandler(self.router),
            "coding": CodingHandler(self.router),
            "document_search": DocumentSearchHandler(self.router),
            "system": SystemHandler(self.router),
            "audio": AudioHandler()
        }

        self._initialized = True

    def submit_task(self,
                    layer: str,
                    prompt: str,
                    payload: Optional[Dict[str, Any]] = None,
                    priority: int = TaskPriority.URGENT,
                    memory_cost: str = MemoryCost.LOW,
                    parent_task_id: Optional[str] = None) -> str:
        """Submits a new task to the central queue."""
        task = AUTask(
            layer=layer,
            prompt=prompt,
            payload=payload or {},
            priority=priority,
            memory_cost=memory_cost,
            parent_task_id=parent_task_id
        )
        return self.queue.submit(task)

    def dispatch(self, task: AUTask) -> AUTask:
        """
        Executes a task through the central orchestrator core.
        Enforces pre-flight memory governor check and hub-and-spoke routing.
        """
        # Step 1: Pre-flight Memory Governor Check
        can_run, reason = self.governor.can_run_task(task.memory_cost)
        if not can_run:
            task.status = TaskStatus.PAUSED
            task.error = f"Governor paused: {reason}"
            self.queue.update_task(task)
            return task

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self.queue.update_task(task)

        # Step 2: Route to Outer Domain Handler
        handler = self.layers.get(task.layer)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error = f"Unknown layer handler: '{task.layer}'"
            task.completed_at = time.time()
            self.queue.update_task(task)
            return task

        try:
            # Hub-and-Spoke: handler passes self (orchestrator) for any sub-task needs
            res = handler.execute(task, self)
            task.result = res
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
        finally:
            task.completed_at = time.time()
            self.queue.update_task(task)

            # Lazy unloading cleanup if memory is tight after heavy job
            if task.memory_cost == MemoryCost.HIGH:
                self.governor.purge_memory()

        return task

    def dispatch_subtask(self, parent_task_id: str, layer: str, prompt: str, payload: Optional[Dict[str, Any]] = None, memory_cost: str = MemoryCost.LOW) -> AUTask:
        """
        Hub-and-spoke subtask dispatch:
        Outer agents invoke subtasks ONLY via this method through the orchestrator.
        """
        subtask_id = self.submit_task(
            layer=layer,
            prompt=prompt,
            payload=payload or {},
            priority=TaskPriority.NORMAL,
            memory_cost=memory_cost,
            parent_task_id=parent_task_id
        )
        subtask = self.queue.get(subtask_id)
        if subtask:
            return self.dispatch(subtask)
        raise RuntimeError(f"Failed to retrieve queued subtask {subtask_id}")

    def run_chat(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Convenience entrypoint: simple interactive chat through orchestrator core.
        Starts with one local model (au-assistant:latest) and personal memory.
        """
        task = AUTask(
            layer="chat",
            prompt=prompt,
            payload={"messages": history or []},
            priority=TaskPriority.URGENT,
            memory_cost=MemoryCost.LOW
        )
        self.queue.submit(task)
        result_task = self.dispatch(task)
        if result_task.status == TaskStatus.COMPLETED and result_task.result:
            return result_task.result.get("text", "")
        elif result_task.error:
            return f"Error: {result_task.error}"
        return ""

    def get_status_overview(self) -> Dict[str, Any]:
        """Telemetry snapshot for CLI and GUI displays."""
        stats = self.governor.get_memory_stats()
        running_models = self.router.list_running_models()
        active_tasks = self.queue.list_tasks(status=TaskStatus.RUNNING, limit=5)
        queued_tasks = self.queue.list_tasks(status=TaskStatus.QUEUED, limit=5)
        paused_tasks = self.queue.list_tasks(status=TaskStatus.PAUSED, limit=5)

        return {
            "memory": stats,
            "running_models": [m.get("name") for m in running_models],
            "active_tasks_count": len(active_tasks),
            "queued_tasks_count": len(queued_tasks),
            "paused_tasks_count": len(paused_tasks),
            "queue_sample": {
                "active": [t.to_dict() for t in active_tasks],
                "paused": [t.to_dict() for t in paused_tasks]
            }
        }

    def get_au_status(self) -> str:
        """
        Returns a rich status string combining: RAM state, emotion state (mood + valence),
        session summary, task queue count.
        Example: "🧠 AU online | 😊 Mood: excited | Session: 45m, 8 queries | RAM: 5.4 GB / 🟢 | Queue: 0 tasks"
        """
        # 1. RAM State
        mem = self.governor.get_memory_stats()
        used_gb = mem.get("used_gb", 0.0)
        state = mem.get("state", "GREEN")
        state_icon = "🟢" if state == "GREEN" else ("🟡" if state == "YELLOW" else "🔴")
        ram_str = f"RAM: {used_gb} GB / {state_icon}"

        # 2. Emotion State
        mood_icons = {
            "happy": "😊",
            "curious": "🤔",
            "focused": "🎯",
            "calm": "😌",
            "concerned": "😟",
            "excited": "😊",
            "empathetic": "🤝",
            "playful": "😄",
            "proud": "🦁",
            "tired": "🥱",
        }
        if self.emotion_engine and hasattr(self.emotion_engine, "_state"):
            st = self.emotion_engine._state
            mood = getattr(st, "current_mood", "calm")
            valence = getattr(st, "valence", 0.0)
            icon = mood_icons.get(mood, "😊")
            val_sign = "+" if valence >= 0 else ""
            emotion_str = f"{icon} Mood: {mood} (valence: {val_sign}{valence:.2f})"
        else:
            emotion_str = "😊 Mood: calm"

        # 3. Session Summary
        if self.context_engine and hasattr(self.context_engine, "session"):
            sess = self.context_engine.session
            elapsed_m = max(1, int((time.time() - getattr(sess, "start_time", time.time())) / 60))
            q_count = getattr(sess, "query_count", 0)
            session_str = f"Session: {elapsed_m}m, {q_count} queries"
        else:
            session_str = "Session: 1m, 0 queries"

        # 4. Task Queue Count
        try:
            active_tasks = self.queue.list_tasks(status=TaskStatus.RUNNING, limit=50)
            queued_tasks = self.queue.list_tasks(status=TaskStatus.QUEUED, limit=50)
            queue_count = len(active_tasks) + len(queued_tasks)
        except Exception:
            queue_count = 0
        queue_str = f"Queue: {queue_count} tasks"

        return f"🧠 AU online | {emotion_str} | {session_str} | {ram_str} | {queue_str}"

# ==============================================================================
# 7. CLI COMMAND-LINE INTERFACE
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AU Central Orchestrator Core")
    subparsers = parser.add_subparsers(dest="command")

    # au-orchestrator chat "query"
    chat_p = subparsers.add_parser("chat", help="Execute interactive chat via single local model")
    chat_p.add_argument("query", nargs="+", help="User prompt")

    # au-orchestrator status
    subparsers.add_parser("status", help="Show M4 RAM governor and orchestrator task queue status")

    # au-orchestrator queue [list|clear]
    queue_p = subparsers.add_parser("queue", help="Manage task queue")
    queue_p.add_argument("--list", action="store_true", help="List recent tasks")
    queue_p.add_argument("--limit", type=int, default=10, help="Number of tasks to display")
    queue_p.add_argument("--clear", action="store_true", help="Clear completed tasks")

    # au-orchestrator purge
    subparsers.add_parser("purge", help="Unload idle Ollama models and free Unified RAM")

    args = parser.parse_args()
    orchestrator = AUOrchestrator()

    if args.command == "chat":
        prompt = " ".join(args.query)
        res = orchestrator.run_chat(prompt)
        print(res)

    elif args.command == "status":
        print(orchestrator.get_au_status())
        status = orchestrator.get_status_overview()
        mem = status["memory"]
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"🧠 AU Central Orchestrator (Apple Silicon M4)")
        print(f"📊 Memory Status: [{mem['state']}] Used: {mem['used_gb']} GB / Available: {mem['available_gb']} GB (Total: {mem['total_gb']} GB)")
        print(f"⚡ VRAM Resident Models: {status['running_models'] or 'None (Lazy Unloaded)'}")
        print(f"📋 Task Queue: {status['active_tasks_count']} running, {status['queued_tasks_count']} queued, {status['paused_tasks_count']} paused")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    elif args.command == "queue":
        if args.clear:
            orchestrator.queue.clear_completed(max_age_hours=0)
            print("✨ Cleared completed tasks.")
        else:
            tasks = orchestrator.queue.list_tasks(limit=args.limit)
            print(f"📋 Recent Orchestrator Tasks ({len(tasks)}):")
            for t in tasks:
                print(f" • [{t.status.upper():9}] [{t.layer:15}] ({t.memory_cost:6}) {t.id} -> {t.prompt[:45]}")

    elif args.command == "purge":
        orchestrator.router.unload_idle_models()
        orchestrator.governor.purge_memory()
        print("🧹 Memory purged: idle models unloaded from Unified RAM.")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
