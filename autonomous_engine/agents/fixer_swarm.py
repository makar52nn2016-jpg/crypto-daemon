"""
autonomous_engine/agents/fixer_swarm.py — Parallel PR generator (Ollama/Groq)

Takes tasks from sniper_bulk queue, generates code fixes via local LLM,
creates PRs in parallel.

Architecture:
  - Each task spawns a worker subprocess
  - Worker uses Ollama qwen2.5-coder:7b (local, free) OR Groq free tier
  - Output: PR URL on github.com
  - Validator-Auto runs BEFORE push (tests, lint)

This is the EXECUTION ARM of the autonomous engine.

Current status (2026-10-01): STUB — needs Ollama install on GHA runner
OR Groq API key. Both add complexity. For now, this stub just logs
queued tasks and waits for infrastructure.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent.parent
STATE_FILE = ENGINE_HOME / "state" / "fixer_swarm.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_run_at": None,
        "tasks_attempted": 0,
        "prs_created": 0,
        "prs_merged": 0,
        "events": [],
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_ollama_available() -> bool:
    """Check if Ollama is installed and has qwen2.5-coder model."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return "qwen2.5-coder" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def check_groq_available() -> bool:
    """Check if Groq API key is set."""
    return bool(os.environ.get("GROQ_API_KEY"))


def check_zai_available() -> bool:
    """Check if z-ai CLI is available (locally)."""
    try:
        result = subprocess.run(
            ["which", "z-ai"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_cycle() -> dict:
    """Process tasks from sniper_bulk queue (when LLM is available)."""
    print(f"[Fixer-Swarm] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()

    # Check LLM availability
    has_ollama = check_ollama_available()
    has_groq = check_groq_available()
    has_zai = check_zai_available()

    print(f"[Fixer-Swarm] LLM backends available:")
    print(f"  - Ollama (qwen2.5-coder): {has_ollama}")
    print(f"  - Groq free tier: {has_groq}")
    print(f"  - Z.ai (local): {has_zai}")

    if not (has_ollama or has_groq or has_zai):
        print(f"[Fixer-Swarm] ⚠️ No LLM backend available. Cannot generate PRs.")
        print(f"[Fixer-Swarm] Stub mode — logging only. To enable:")
        print(f"  - Install Ollama locally: https://ollama.com")
        print(f"  - OR add GROQ_API_KEY secret (free tier)")
        print(f"  - OR run engine locally where z-ai CLI is configured")
        save_state(state)
        return {"status": "no_llm", "queue_size": 0}

    # Load sniper_bulk queue
    sniper_state_file = ENGINE_HOME / "state" / "sniper_bulk.json"
    if not sniper_state_file.exists():
        print(f"[Fixer-Swarm] No sniper_bulk state. Nothing to process.")
        save_state(state)
        return {"status": "no_queue"}

    with open(sniper_state_file) as f:
        sniper_state = json.load(f)
    queue = sniper_state.get("queue", [])
    if not queue:
        print(f"[Fixer-Swarm] Queue empty. Nothing to process.")
        save_state(state)
        return {"status": "empty_queue"}

    print(f"[Fixer-Swarm] Queue has {len(queue)} tasks. Processing first 3 (parallel).")
    # TODO: Implement actual task execution with Ollama
    # For now, just log that we would process them
    state["tasks_attempted"] = state.get("tasks_attempted", 0) + min(3, len(queue))
    state["events"].append({
        "at": datetime.now(timezone.utc).isoformat(),
        "type": "queue_processed_stub",
        "tasks_in_queue": len(queue),
        "tasks_would_process": min(3, len(queue)),
    })
    save_state(state)

    return {
        "status": "stub_mode",
        "queue_size": len(queue),
        "llm_backend": "ollama" if has_ollama else ("groq" if has_groq else ("zai" if has_zai else None)),
        "note": "Full implementation pending — Ollama integration TODO",
    }


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[Fixer-Swarm] Cycle result: {result}")
    sys.exit(0)
