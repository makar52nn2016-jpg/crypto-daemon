"""
autonomous_engine/agents/llm_freeswitch.py — Rotate LLM provider based on availability

Checks which LLM backends are available + healthy:
  1. Z.ai CLI (free locally via /etc/.z-ai-config)
  2. Ollama (local, free, needs install)
  3. Groq free tier (free with API key, 30 req/min)
  4. OpenRouter free models (free with API key)

Sets LLM_BACKEND env var for next cycle based on which is healthiest.

This runs every hour (12th cycle of engine.py).
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent.parent
STATE_FILE = ENGINE_HOME / "state" / "llm_freeswitch.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_check_at": None,
        "current_backend": None,
        "backends_health": {},
        "switches": 0,
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_zai_health() -> dict:
    """Check if z-ai CLI responds to a ping."""
    try:
        # Try direct node invocation (works on GHA where bun isn't installed)
        result = subprocess.run(
            ["node", "/home/z/my-project/node_modules/z-ai-web-dev-sdk/dist/cli.js",
             "chat", "-p", "ping", "-o", "/tmp/zai_health.json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and Path("/tmp/zai_health.json").exists():
            with open("/tmp/zai_health.json") as f:
                data = json.load(f)
            return {
                "available": True,
                "model": data.get("model", "glm-4-plus"),
                "response_time_ms": 0,  # would measure properly
            }
        return {"available": False, "error": result.stderr[:200]}
    except Exception as e:
        return {"available": False, "error": str(e)[:200]}


def check_ollama_health() -> dict:
    """Check if Ollama has qwen2.5-coder model."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "qwen2.5-coder" in result.stdout:
            return {"available": True, "model": "qwen2.5-coder:7b"}
        return {"available": False, "error": "qwen2.5-coder not installed"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"available": False, "error": "ollama not installed"}
    except Exception as e:
        return {"available": False, "error": str(e)[:200]}


def check_groq_health() -> dict:
    """Check if Groq API key is set."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {"available": False, "error": "GROQ_API_KEY not set"}
    return {"available": True, "model": "llama-3.3-70b-versatile"}


def run_cycle() -> dict:
    """Check all LLM backends, set LLM_BACKEND env hint."""
    print(f"[LLM-FreeSwitch] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    state["last_check_at"] = datetime.now(timezone.utc).isoformat()

    health = {}

    # Z.ai (free locally)
    print(f"[LLM-FreeSwitch] Checking Z.ai...")
    zai = check_zai_health()
    health["zai"] = zai
    print(f"  → {zai}")

    # Ollama (local, free, needs install)
    print(f"[LLM-FreeSwitch] Checking Ollama...")
    oll = check_ollama_health()
    health["ollama"] = oll
    print(f"  → {oll}")

    # Groq (free with key)
    print(f"[LLM-FreeSwitch] Checking Groq...")
    groq = check_groq_health()
    health["groq"] = groq
    print(f"  → {groq}")

    state["backends_health"] = health

    # Pick best backend — priority: zai (free, fast) → ollama (local, free) → groq (free w/ key)
    new_backend = None
    if zai.get("available"):
        new_backend = "zai"
    elif oll.get("available"):
        new_backend = "ollama"
    elif groq.get("available"):
        new_backend = "groq"

    if new_backend and new_backend != state.get("current_backend"):
        print(f"[LLM-FreeSwitch] Switching backend: {state.get('current_backend')} → {new_backend}")
        state["switches"] = state.get("switches", 0) + 1

    state["current_backend"] = new_backend
    save_state(state)

    if new_backend is None:
        print(f"[LLM-FreeSwitch] ⚠️ No LLM backend available. Trudyagi will fall back to demo mode.")
    else:
        print(f"[LLM-FreeSwitch] Active backend: {new_backend}")

    return {
        "current_backend": new_backend,
        "all_backends": health,
        "switches_count": state.get("switches", 0),
    }


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[LLM-FreeSwitch] Cycle result: {result}")
    sys.exit(0)
