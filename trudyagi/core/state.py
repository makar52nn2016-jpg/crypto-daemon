"""
trudyagi/core/state.py — Task state machine + per-task state.json

State flow:
    PENDING → PLANNING → EXECUTING → REVIEWING → COMPLETED
                         ↓               ↓
                       FAILED         NEEDS_REVISION (→ EXECUTING again)

Each task lives at tasks/<task_id>/ with:
    - state.json (this module's responsibility)
    - brigadir.yaml (goal + subtasks)
    - master_plan.yaml (steps from Мастер)
    - operator_report.yaml (execution results)
    - controller_review.yaml (verdict)
    - step-N.json (per-step artifacts)
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

# State machine definition
VALID_STATES = {
    "PENDING",         # task created, waiting for Бригадир
    "PLANNING",        # Мастер creating plan
    "EXECUTING",       # Оператор running steps
    "REVIEWING",        # Контролёр verifying
    "NEEDS_REVISION",  # Контролёр found issues, back to EXECUTING
    "COMPLETED",       # all checks PASS
    "FAILED",          # unrecoverable error
}

VALID_TRANSITIONS = {
    "PENDING": {"PLANNING", "FAILED"},
    "PLANNING": {"EXECUTING", "FAILED"},
    "EXECUTING": {"REVIEWING", "FAILED"},
    "REVIEWING": {"COMPLETED", "NEEDS_REVISION", "FAILED"},
    "NEEDS_REVISION": {"EXECUTING", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}

# Roles in pipeline order
ROLE_ORDER = ["brigadir", "master", "operator", "controller"]


class TaskState:
    """Manages state.json for a single task."""

    def __init__(self, task_id: str, tasks_dir: str = "tasks"):
        self.task_id = task_id
        self.tasks_dir = Path(tasks_dir)
        self.task_dir = self.tasks_dir / task_id
        self.state_file = self.task_dir / "state.json"
        self.task_dir.mkdir(parents=True, exist_ok=True)

    def init(self, goal: str, demo: bool = False) -> dict:
        """Create a fresh task with PENDING state."""
        state = {
            "task_id": self.task_id,
            "goal": goal,
            "state": "PENDING",
            "demo_mode": demo,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "current_role": None,
            "history": [],
            "artifacts": [],
        }
        self._write(state)
        return state

    def load(self) -> dict:
        """Load current state from disk."""
        if not self.state_file.exists():
            raise FileNotFoundError(f"State file not found: {self.state_file}")
        with open(self.state_file) as f:
            return json.load(f)

    def transition(self, new_state: str, role: str | None = None, note: str = "") -> dict:
        """Move to new_state, with optional role context."""
        state = self.load()
        old_state = state["state"]

        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}. Valid: {VALID_STATES}")
        if new_state not in VALID_TRANSITIONS.get(old_state, set()):
            raise ValueError(f"Invalid transition: {old_state} → {new_state}")

        state["state"] = new_state
        state["current_role"] = role
        state["updated_at"] = int(time.time())
        state["history"].append({
            "at": int(time.time()),
            "from": old_state,
            "to": new_state,
            "role": role,
            "note": note,
        })
        self._write(state)
        return state

    def add_artifact(self, name: str, path: str) -> None:
        """Register an artifact file (e.g., operator's step-N.json)."""
        state = self.load()
        state["artifacts"].append({
            "name": name,
            "path": path,
            "added_at": int(time.time()),
        })
        state["updated_at"] = int(time.time())
        self._write(state)

    def save_role_output(self, role: str, content: str) -> Path:
        """Save a role's output (YAML) to the task dir."""
        filename = f"{role}.yaml" if role != "operator" else "operator_report.yaml"
        if role == "controller":
            filename = "controller_review.yaml"
        if role == "master":
            filename = "master_plan.yaml"
        if role == "brigadir":
            filename = "brigadir.yaml"
        path = self.task_dir / filename
        path.write_text(content, encoding="utf-8")
        self.add_artifact(filename, str(path))
        return path

    def list_artifacts(self) -> list[Path]:
        """List all artifact files in the task dir."""
        return sorted(p for p in self.task_dir.iterdir() if p.is_file())

    def _write(self, state: dict) -> None:
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


def new_task_id() -> str:
    """Generate a short unique task ID."""
    return f"task-{uuid.uuid4().hex[:8]}"


def list_all_tasks(tasks_dir: str = "tasks") -> list[dict]:
    """List all tasks (most recent first)."""
    tasks_path = Path(tasks_dir)
    if not tasks_path.exists():
        return []
    tasks = []
    for task_dir in tasks_path.iterdir():
        if not task_dir.is_dir():
            continue
        state_file = task_dir / "state.json"
        if not state_file.exists():
            continue
        try:
            with open(state_file) as f:
                state = json.load(f)
            tasks.append(state)
        except (json.JSONDecodeError, OSError):
            continue
    tasks.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return tasks
