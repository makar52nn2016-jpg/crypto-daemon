"""
trudyagi/core/orchestrator.py — 4-role pipeline coordinator

Pipeline:
    1. Бригадир  receives user goal → produces subtasks (brigadir.yaml)
    2. Мастер    receives subtask → produces plan (master_plan.yaml)
    3. Оператор  executes plan → produces step artifacts (operator_report.yaml + step-N.json)
    4. Контролёр verifies artifacts → produces verdict (controller_review.yaml)

If verdict is NEEDS_REVISION → loop back to step 3 (Мастер creates revised plan).
If verdict is FAIL → task ends with FAILED state.
If verdict is PASS → task ends with COMPLETED state.

The orchestrator calls one LLM per role. Each call is independent and stateless —
the orchestrator passes the previous role's output as context.
"""

import json
import os
import subprocess
import time
import re
from pathlib import Path
from typing import Optional

from .state import TaskState, new_task_id, ROLE_ORDER
from .llm_client import LLMClient, load_role_prompt
from .demo_llm import DemoLLMClient
from . import worklog


def _strip_yaml_fence(text: str) -> str:
    """Strip ```yaml ... ``` fence if present."""
    match = re.search(r"```ya?ml\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _make_llm(demo: bool = False):
    """Construct the appropriate LLM client."""
    if demo:
        return DemoLLMClient()
    return LLMClient()


def run_pipeline(
    goal: str,
    demo: bool = False,
    tasks_dir: str = "tasks",
    worklog_path: Optional[Path] = None,
    max_revisions: int = 2,
) -> dict:
    """Run the full 4-role pipeline for a single goal.

    Returns the final task state dict.
    """
    task_id = new_task_id()
    task = TaskState(task_id, tasks_dir=tasks_dir)
    task.init(goal, demo=demo)

    roles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "roles")

    # --- Step 1: Бригадир ---
    task.transition("PLANNING", role="brigadir", note="Бригадир parsing goal")
    t0 = time.time()
    brigadir_prompt = load_role_prompt("brigadir", roles_dir=roles_dir)
    llm = _make_llm(demo=demo)
    brigadir_output = llm.chat(brigadir_prompt, goal)
    brigadir_output = _strip_yaml_fence(brigadir_output)
    task.save_role_output("brigadir", brigadir_output)
    worklog.log_step(
        task_id=task_id,
        role="Бригадир",
        step_desc=f"Parsed goal → subtasks",
        duration_sec=time.time() - t0,
        artifact_path=str(task.task_dir / "brigadir.yaml"),
        worklog_path=worklog_path,
    )

    # --- Step 2: Мастер ---
    t0 = time.time()
    master_prompt = load_role_prompt("master", roles_dir=roles_dir)
    master_output = llm.chat(master_prompt, brigadir_output)
    master_output = _strip_yaml_fence(master_output)
    task.save_role_output("master", master_output)
    worklog.log_step(
        task_id=task_id,
        role="Мастер",
        step_desc="Created technical plan",
        duration_sec=time.time() - t0,
        artifact_path=str(task.task_dir / "master_plan.yaml"),
        worklog_path=worklog_path,
    )

    # --- Steps 3 + 4: Operator + Controller loop ---
    revisions = 0
    while revisions <= max_revisions:
        # --- Step 3: Оператор ---
        task.transition("EXECUTING", role="operator", note=f"Operator run (attempt {revisions + 1})")
        t0 = time.time()
        operator_prompt = load_role_prompt("operator", roles_dir=roles_dir)
        operator_output = llm.chat(operator_prompt, master_output)
        operator_output = _strip_yaml_fence(operator_output)
        task.save_role_output("operator", operator_output)

        # Execute any real shell commands mentioned in operator output
        # (in demo mode these are simulated; in real mode, the operator returns
        # commands and we run them here, saving outputs as step-N.json artifacts)
        executed_artifacts = _execute_operator_steps(operator_output, task.task_dir)
        for art in executed_artifacts:
            task.add_artifact(art["name"], art["path"])

        worklog.log_step(
            task_id=task_id,
            role="Оператор",
            step_desc=f"Executed plan (attempt {revisions + 1})",
            duration_sec=time.time() - t0,
            artifact_path=str(task.task_dir / "operator_report.yaml"),
            worklog_path=worklog_path,
        )

        # --- Step 4: Контролёр ---
        task.transition("REVIEWING", role="controller", note="Controller verifying")
        t0 = time.time()
        controller_prompt = load_role_prompt("controller", roles_dir=roles_dir)
        controller_input = f"""Plan from Мастер:
{master_output}

Report from Оператор:
{operator_output}
"""
        controller_output = llm.chat(controller_prompt, controller_input)
        controller_output = _strip_yaml_fence(controller_output)
        task.save_role_output("controller", controller_output)
        worklog.log_step(
            task_id=task_id,
            role="Контролёр",
            step_desc="Verified operator output",
            duration_sec=time.time() - t0,
            artifact_path=str(task.task_dir / "controller_review.yaml"),
            worklog_path=worklog_path,
        )

        # Parse verdict (look for "verdict: PASS|FAIL|NEEDS_REVISION")
        verdict_match = re.search(r"verdict:\s*(PASS|FAIL|NEEDS_REVISION)", controller_output)
        verdict = verdict_match.group(1) if verdict_match else "FAIL"

        if verdict == "PASS":
            task.transition("COMPLETED", role="controller", note="All checks passed")
            worklog.append_entry(
                task_id=task_id,
                agent="Trudyagi orchestrator",
                task=goal,
                work_log=[f"Pipeline COMPLETED after {revisions + 1} operator attempt(s)"],
                stage_summary=[f"Final verdict: PASS — task {task_id} completed"],
                worklog_path=worklog_path,
            )
            return task.load()

        if verdict == "FAIL":
            task.transition("FAILED", role="controller", note="Critical issue, cannot recover")
            worklog.append_entry(
                task_id=task_id,
                agent="Trudyagi orchestrator",
                task=goal,
                work_log=[f"Pipeline FAILED after {revisions + 1} attempt(s)"],
                stage_summary=[f"Final verdict: FAIL — task {task_id} failed"],
                worklog_path=worklog_path,
            )
            return task.load()

        # NEEDS_REVISION — loop back to operator
        revisions += 1
        if revisions > max_revisions:
            task.transition("FAILED", role="controller", note=f"Max revisions ({max_revisions}) exceeded")
            worklog.append_entry(
                task_id=task_id,
                agent="Trudyagi orchestrator",
                task=goal,
                work_log=[f"Pipeline EXHAUSTED {max_revisions} revisions"],
                stage_summary=[f"Final verdict: FAIL — task {task_id} exceeded max revisions"],
                worklog_path=worklog_path,
            )
            return task.load()

        task.transition("NEEDS_REVISION", role="controller", note=f"Revision needed ({revisions}/{max_revisions})")
        worklog.log_step(
            task_id=task_id,
            role="Контролёр",
            step_desc=f"NEEDS_REVISION — operator retry ({revisions}/{max_revisions})",
            duration_sec=0.0,
            worklog_path=worklog_path,
        )

    # Should never reach here
    task.transition("FAILED", role="orchestrator", note="Unexpected loop exit")
    return task.load()


def _execute_operator_steps(operator_yaml: str, task_dir: Path) -> list[dict]:
    """Extract and execute real shell commands from operator's report.

    Looks for 'command: <bash>' lines and executes them. Saves output as
    step-N.json. Skips commands that look unsafe (rm -rf, sudo, etc).

    This is a v1 — in real mode, the LLM is supposed to OUTPUT commands
    that the orchestrator then runs. The orchestrator acts as the trusted
    execution environment with the operator's commands reviewed against
    a safety list.

    Args:
        operator_yaml: the operator's YAML report (string)
        task_dir: path to the task's directory

    Returns:
        List of artifacts produced.
    """
    artifacts = []
    # Find all 'command: <text>' lines
    commands = re.findall(r"^\s*command:\s*(.+)$", operator_yaml, re.MULTILINE)
    if not commands:
        return artifacts

    # Safety: block dangerous patterns
    BLOCKED_PATTERNS = [
        r"\brm\s+-rf\b",
        r"\bsudo\b",
        r"\bmkfs\b",
        r"\bdd\b.*of=",
        r">\s*/dev/sd",
        r":\(\)\{",  # fork bomb
    ]
    for i, cmd in enumerate(commands, 1):
        cmd = cmd.strip().strip("'\"")
        if any(re.search(p, cmd) for p in BLOCKED_PATTERNS):
            artifact = {
                "name": f"step-{i}-BLOCKED.json",
                "path": str(task_dir / f"step-{i}-BLOCKED.json"),
            }
            (task_dir / artifact["path"]).write_text(json.dumps({
                "command": cmd,
                "blocked": True,
                "reason": "matches dangerous pattern",
            }, indent=2), encoding="utf-8")
            artifacts.append(artifact)
            continue

        # Run the command
        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout[:2000] if result.stdout else ""
            error = result.stderr[:2000] if result.stderr else ""
            status = "SUCCESS" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
        except subprocess.TimeoutExpired:
            output, error = "", "TIMEOUT after 60s"
            status = "TIMEOUT"
        except Exception as e:
            output, error = "", str(e)[:500]
            status = "ERROR"

        artifact_path = task_dir / f"step-{i}.json"
        artifact_path.write_text(json.dumps({
            "step_id": f"step-{i}",
            "command": cmd,
            "status": status,
            "stdout": output,
            "stderr": error,
            "duration_sec": round(time.time() - t0, 2),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        artifacts.append({
            "name": f"step-{i}.json",
            "path": str(artifact_path),
        })

    return artifacts
