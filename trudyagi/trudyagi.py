#!/usr/bin/env python3
"""
trudyagi.py — CLI entry point for the 4-role autonomous agent corporation

Commands:
    init              Create .env from .env.example (interactive)
    run "<goal>"      Run full pipeline for a goal (real LLM)
    demo "<goal>"     Run pipeline with mock LLM (no API key needed)
    status [task_id]  Show current/last task status
    history [N]       Show last N tasks (default 10)
    worklog [N]       Show last N worklog entries
    health            Quick health check of LLM API

Usage:
    python trudyagi.py demo "Earn $1.50 today via Frantic #136"
    python trudyagi.py init
    python trudyagi.py status
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add this file's directory to sys.path so `core` can be imported
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from core import run_pipeline, list_all_tasks, LLMClient, DemoLLMClient  # noqa: E402
from core import worklog as worklog_mod  # noqa: E402


ENV_TEMPLATE = """# Trudyagi configuration — OpenAI-compatible LLM
# Tested with: OpenAI, Anthropic via openai-compat, Z.ai GLM, Ollama

# Required for `run` command (skip for `demo` mode)
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Optional tuning
LLM_MAX_TOKENS=1500
LLM_TEMPERATURE=0.3

# Shared worklog path (auto-detected if not set)
# TRUDYAGI_WORKLOG=/home/z/my-project/worklog.md
"""


def cmd_init(args):
    """Create .env from template."""
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists() and not args.force:
        print(f"✅ .env already exists at {env_path}")
        print("   Use --force to overwrite.")
        return 0

    env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    print(f"✅ Created {env_path}")
    print()
    print("Next steps:")
    print("  1. Edit .env — fill in LLM_API_KEY, LLM_BASE_URL, LLM_MODEL")
    print("  2. Test:     python trudyagi.py health")
    print("  3. Demo run: python trudyagi.py demo 'Earn $1.50 today'")
    print("  4. Real run: python trudyagi.py run 'Earn $1.50 today'")
    return 0


def cmd_run(args):
    """Run pipeline with real LLM."""
    _load_env()
    return _run_pipeline(args.goal, demo=False)


def cmd_demo(args):
    """Run pipeline with mock LLM (no API key needed)."""
    return _run_pipeline(args.goal, demo=True)


def _run_pipeline(goal: str, demo: bool) -> int:
    print(f"{'🎭 DEMO' if demo else '🚀 LIVE'} mode — running pipeline for:")
    print(f"   \"{goal}\"")
    print()

    try:
        final_state = run_pipeline(goal=goal, demo=demo, tasks_dir=str(SCRIPT_DIR / "tasks"))
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        return 1

    print()
    print("=" * 60)
    print(f"Final state: {final_state['state']}")
    print(f"Task ID:     {final_state['task_id']}")
    print(f"Goal:        {final_state['goal']}")
    print()
    print(f"Artifacts in tasks/{final_state['task_id']}/:")
    for art in final_state.get("artifacts", []):
        print(f"  - {art['name']}")
    print()
    print("Worklog updated. View with: python trudyagi.py worklog 3")
    return 0 if final_state["state"] == "COMPLETED" else 1


def cmd_status(args):
    """Show current task status."""
    tasks = list_all_tasks(str(SCRIPT_DIR / "tasks"))
    if not tasks:
        print("📭 No tasks yet. Run: python trudyagi.py demo \"<goal>\"")
        return 0

    if args.task_id:
        # Find specific task
        task = next((t for t in tasks if t["task_id"] == args.task_id), None)
        if not task:
            print(f"❌ Task {args.task_id} not found")
            return 1
        _print_task_detail(task)
    else:
        # Show latest task
        latest = tasks[0]
        _print_task_detail(latest)
    return 0


def cmd_history(args):
    """Show last N tasks."""
    tasks = list_all_tasks(str(SCRIPT_DIR / "tasks"))
    if not tasks:
        print("📭 No tasks yet.")
        return 0

    n = args.limit
    print(f"📜 Last {min(n, len(tasks))} task(s):\n")
    for t in tasks[:n]:
        emoji = {
            "COMPLETED": "✅",
            "FAILED": "❌",
            "PENDING": "⏳",
            "PLANNING": "🧠",
            "EXECUTING": "⚙️",
            "REVIEWING": "🔍",
            "NEEDS_REVISION": "🔧",
        }.get(t["state"], "❓")
        goal_preview = t["goal"][:60]
        print(f"  {emoji} {t['task_id']} | {t['state']:14} | {goal_preview}")
    return 0


def cmd_worklog(args):
    """Show recent worklog entries."""
    entries = worklog_mod.read_recent_entries(n=args.limit)
    if not entries:
        print("📭 Worklog is empty. Run a task first.")
        return 0

    print(f"📝 Last {len(entries)} worklog entr{'y' if len(entries) == 1 else 'ies'}:\n")
    for entry in entries:
        print(entry)
        print("---")
    return 0


def cmd_health(args):
    """Quick LLM health check."""
    _load_env()
    print("🔍 Health check...")
    try:
        client = LLMClient()
        if client.is_alive():
            print(f"  ✅ LLM API alive")
            print(f"     Base URL: {client.base_url}")
            print(f"     Model:    {client.model}")
            return 0
        else:
            print(f"  ❌ LLM API not responding")
            print(f"     Base URL: {client.base_url}")
            print(f"     Model:    {client.model}")
            print(f"     Check LLM_API_KEY in .env")
            return 1
    except ValueError as e:
        print(f"  ❌ Config error: {e}")
        print(f"     Run: python trudyagi.py init")
        return 1


def _load_env():
    """Load .env file (simple key=value parser)."""
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            # Only set if not already in env (don't override env vars)
            if key and key not in os.environ:
                os.environ[key] = value


def _print_task_detail(task: dict):
    """Print detailed task info."""
    print(f"📋 Task: {task['task_id']}")
    print(f"   State:  {task['state']}")
    print(f"   Goal:   {task['goal']}")
    print(f"   Demo:   {task.get('demo_mode', False)}")
    print(f"   Created: {task.get('created_at', '?')}")
    print(f"   Updated: {task.get('updated_at', '?')}")
    print(f"   Role:   {task.get('current_role', 'none')}")
    print()
    print(f"   History ({len(task.get('history', []))} transitions):")
    for h in task.get("history", [])[-5:]:
        print(f"     {h['from']} → {h['to']} (by {h.get('role', '?')}): {h.get('note', '')}")
    print()
    print(f"   Artifacts ({len(task.get('artifacts', []))}):")
    for art in task.get("artifacts", []):
        print(f"     - {art['name']}")


def main():
    parser = argparse.ArgumentParser(
        prog="trudyagi",
        description="4-role autonomous agent corporation (Бригадир/Мастер/Контролёр/Оператор)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Create .env from template")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing .env")
    p_init.set_defaults(func=cmd_init)

    # run (real LLM)
    p_run = sub.add_parser("run", help="Run pipeline with real LLM")
    p_run.add_argument("goal", help="The goal to accomplish")
    p_run.set_defaults(func=cmd_run)

    # demo (mock LLM)
    p_demo = sub.add_parser("demo", help="Run pipeline with mock LLM (no API key needed)")
    p_demo.add_argument("goal", help="The goal to accomplish")
    p_demo.set_defaults(func=cmd_demo)

    # status
    p_status = sub.add_parser("status", help="Show current/last task status")
    p_status.add_argument("task_id", nargs="?", help="Specific task ID to show")
    p_status.set_defaults(func=cmd_status)

    # history
    p_history = sub.add_parser("history", help="List recent tasks")
    p_history.add_argument("limit", type=int, nargs="?", default=10, help="Max tasks to show")
    p_history.set_defaults(func=cmd_history)

    # worklog
    p_worklog = sub.add_parser("worklog", help="Show recent worklog entries")
    p_worklog.add_argument("limit", type=int, nargs="?", default=5, help="Max entries to show")
    p_worklog.set_defaults(func=cmd_worklog)

    # health
    p_health = sub.add_parser("health", help="Quick LLM API health check")
    p_health.set_defaults(func=cmd_health)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
