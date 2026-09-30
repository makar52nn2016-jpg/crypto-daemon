"""
trudyagi/core/worklog.py — Shared multi-agent worklog integration

All agents (Бригадир, Мастер, Оператор, Контролёр) append entries
to the same worklog file. This makes the whole pipeline auditable.

Protocol:
    - File: /home/z/my-project/worklog.md (when running locally)
            or ./worklog.md (when running on GitHub Actions daemon)
    - Each entry starts with '---' separator
    - Each entry has: Task ID, Agent, Task, Work Log, Stage Summary
"""

import os
import time
from pathlib import Path
from typing import Optional


def find_worklog_path() -> Path:
    """Find the worklog file. Try common locations."""
    # 1. Explicit env var
    if env_path := os.environ.get("TRUDYAGI_WORKLOG"):
        return Path(env_path)
    # 2. /home/z/my-project/worklog.md (local dev)
    p1 = Path("/home/z/my-project/worklog.md")
    if p1.parent.exists():
        return p1
    # 3. ./worklog.md (cwd, e.g. on GitHub Actions runner)
    p2 = Path.cwd() / "worklog.md"
    return p2


def append_entry(
    task_id: str,
    agent: str,
    task: str,
    work_log: list[str],
    stage_summary: list[str],
    worklog_path: Optional[Path] = None,
) -> Path:
    """Append a new entry to the shared worklog.

    Args:
        task_id: e.g. "task-abc12345"
        agent: e.g. "Бригадир (Trudyagi)"
        task: one-line description
        work_log: list of concrete steps taken
        stage_summary: list of key results/decisions/artifacts
        worklog_path: override path (default: auto-detect)

    Returns:
        Path to the worklog file written to.
    """
    worklog_path = worklog_path or find_worklog_path()
    worklog_path.parent.mkdir(parents=True, exist_ok=True)

    entry = f"""---
Task ID: {task_id}
Agent: {agent}
Task: {task}

Work Log:
"""
    for line in work_log:
        entry += f"- {line}\n"

    entry += "\nStage Summary:\n"
    for line in stage_summary:
        entry += f"- {line}\n"

    # Append (don't overwrite)
    with open(worklog_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

    return worklog_path


def log_step(
    task_id: str,
    role: str,
    step_desc: str,
    duration_sec: float,
    artifact_path: Optional[str] = None,
    success: bool = True,
    worklog_path: Optional[Path] = None,
) -> None:
    """Convenience: log a single step. Used by orchestrator."""
    status_emoji = "✅" if success else "❌"
    work_log = [
        f"{status_emoji} [{role}] {step_desc} ({duration_sec:.1f}s)",
    ]
    if artifact_path:
        work_log.append(f"   artifact: {artifact_path}")

    summary = [
        f"Step {'succeeded' if success else 'failed'}: {step_desc}",
    ]

    append_entry(
        task_id=task_id,
        agent=f"{role} (Trudyagi)",
        task=step_desc,
        work_log=work_log,
        stage_summary=summary,
        worklog_path=worklog_path,
    )


def read_recent_entries(n: int = 10, worklog_path: Optional[Path] = None) -> list[str]:
    """Read the last N entries from the worklog. Returns list of entry strings."""
    worklog_path = worklog_path or find_worklog_path()
    if not worklog_path.exists():
        return []
    content = worklog_path.read_text(encoding="utf-8")
    # Split on '---' (each entry starts with ---)
    parts = content.split("\n---\n")
    # First part is empty (file starts with ---)
    entries = [p.strip() for p in parts if p.strip()]
    return entries[-n:]
