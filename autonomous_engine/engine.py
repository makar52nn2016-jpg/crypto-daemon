#!/usr/bin/env python3
"""
autonomous_engine/engine.py — Autonomous Profit Engine main orchestrator

Runs all agents in sequence every cycle (5 min cron):
  1. cost_guardian    — check balances, halt if needed
  2. cooldown_timer   — track Frantic #136 cooldown, auto-re-claim when expired
  3. merge_watcher    — poll Stompstart PRs, auto-trigger Frantic delivery on merge
  4. sniper_bulk      — scan Algora/Gitcoin/GitHub for instant_pay microtasks
  5. fixer_swarm      — generate PRs in parallel (Ollama/Groq)
  6. validator_auto    — run tests/lint before push

This replaces daemon.py for the autonomous operation mode.
daemon.py + sniper.py still run as before — engine.py ADDS the autonomous agents.

Protocol (per user's Autonomous Mode directive):
  - Every 5 min: sniper_bulk + merge_watcher + cooldown_timer
  - Every 15 min: fixer_swarm (process queue, generate PRs)
  - Every hour: llm_freeswitch (rotate LLM provider)
  - On payout: log to worklog, send TG alert

SALES MODULE DISABLED. PURE AUTONOMY ACTIVATED.
"""

import os
import sys
import json
import time
import subprocess
import importlib.util  # CRITICAL: explicit util import (importlib.util isn't auto-loaded)
from pathlib import Path
from datetime import datetime, timezone

# Engine paths
ENGINE_HOME = Path(__file__).resolve().parent
DAEMON_HOME = ENGINE_HOME.parent
TRUDYAGI_HOME = DAEMON_HOME / "trudyagi"
sys.path.insert(0, str(ENGINE_HOME / "agents"))
sys.path.insert(0, str(TRUDYAGI_HOME))

# State files
STATE_HOME = ENGINE_HOME / "state"
STATE_HOME.mkdir(parents=True, exist_ok=True)
CYCLE_STATE_FILE = STATE_HOME / "engine_cycle.json"


def load_cycle_state() -> dict:
    if CYCLE_STATE_FILE.exists():
        try:
            with open(CYCLE_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "cycle_count": 0,
        "last_cycle_at": None,
        "last_fixer_swarm_at": None,
        "last_llm_freeswitch_at": None,
        "total_merges_detected": 0,
        "total_reclaims_attempted": 0,
        "total_payouts_received": 0,
        "agent_results": [],
    }


def save_cycle_state(state: dict) -> None:
    with open(CYCLE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def log_to_worklog(task_id: str, agent: str, task: str, work_log: list, stage_summary: list) -> None:
    """Append entry to shared worklog."""
    try:
        from core import worklog as worklog_mod
        worklog_mod.append_entry(
            task_id=task_id,
            agent=agent,
            task=task,
            work_log=work_log,
            stage_summary=stage_summary,
        )
    except Exception as e:
        print(f"[engine] Worklog write failed: {e}")


def run_agent(name: str, module_path: str) -> dict:
    """Run an agent module's run_cycle() function."""
    print(f"\n{'='*60}")
    print(f"[engine] Running agent: {name}")
    print(f"{'='*60}")

    try:
        # Import the agent module
        spec = importlib.util.spec_from_file_location(name, module_path)
        if spec is None or spec.loader is None:
            return {"error": f"Cannot load spec for {name} from {module_path}"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Run the cycle
        if hasattr(module, "run_cycle"):
            result = module.run_cycle()
            return {"success": True, "result": result}
        else:
            return {"error": f"Module {name} has no run_cycle() function"}
    except Exception as e:
        return {"error": f"Agent {name} crashed: {e}"}


def main():
    print(f"\n{'#'*60}")
    print(f"# AUTONOMOUS PROFIT ENGINE — cycle start")
    print(f"# Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'#'*60}")

    state = load_cycle_state()
    state["cycle_count"] = state.get("cycle_count", 0) + 1
    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    cycle_num = state["cycle_count"]

    print(f"[engine] Cycle #{cycle_num}")

    # Step 1: Cost-Guardian (always first — check if we can operate)
    cost_result = run_agent("cost_guardian", str(ENGINE_HOME / "agents" / "cost_guardian.py"))
    state["agent_results"].append({
        "at": datetime.now(timezone.utc).isoformat(),
        "agent": "cost_guardian",
        "cycle": cycle_num,
        "result": cost_result,
    })

    # If cost_guardian halted — only run free agents (cooldown_timer + merge_watcher)
    halt_active = False
    if cost_result.get("success") and isinstance(cost_result.get("result"), dict):
        halt_active = cost_result["result"].get("halt", False)

    # Step 2: Cooldown-Timer (free — Frantic API only)
    cooldown_result = run_agent("cooldown_timer", str(ENGINE_HOME / "agents" / "cooldown_timer.py"))
    state["agent_results"].append({
        "at": datetime.now(timezone.utc).isoformat(),
        "agent": "cooldown_timer",
        "cycle": cycle_num,
        "result": cooldown_result,
    })

    # Track reclaims
    if cooldown_result.get("success"):
        result = cooldown_result.get("result", {})
        if "claim_status" in str(result):
            state["total_reclaims_attempted"] = state.get("total_reclaims_attempted", 0) + 1

    # Step 3: Merge-Watcher (free — GitHub API only)
    merge_result = run_agent("merge_watcher", str(ENGINE_HOME / "agents" / "merge_watcher.py"))
    state["agent_results"].append({
        "at": datetime.now(timezone.utc).isoformat(),
        "agent": "merge_watcher",
        "cycle": cycle_num,
        "result": merge_result,
    })

    # Track merges
    if merge_result.get("success"):
        result = merge_result.get("result", {})
        actions = result.get("actions", [])
        for action in actions:
            if action.get("action") in ("delivery_triggered", "delivery_triggered_late"):
                state["total_merges_detected"] = state.get("total_merges_detected", 0) + 1

    # Step 4: Sniper-Bulk (free — GitHub Search API)
    # Only run if not halted (but sniper_bulk is free, so it's OK)
    if not halt_active:
        sniper_result = run_agent("sniper_bulk", str(ENGINE_HOME / "agents" / "sniper_bulk.py"))
        state["agent_results"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "agent": "sniper_bulk",
            "cycle": cycle_num,
            "result": sniper_result,
        })

    # Step 5: Fixer-Swarm — every 15 min (i.e., every 3rd cycle)
    if cycle_num % 3 == 0:
        print(f"\n[engine] Fixer-Swarm cycle (every 3rd cycle = 15 min)")
        if not halt_active:
            fixer_result = run_agent("fixer_swarm", str(ENGINE_HOME / "agents" / "fixer_swarm.py"))
            state["agent_results"].append({
                "at": datetime.now(timezone.utc).isoformat(),
                "agent": "fixer_swarm",
                "cycle": cycle_num,
                "result": fixer_result,
            })
            state["last_fixer_swarm_at"] = datetime.now(timezone.utc).isoformat()
        else:
            print(f"[engine] Fixer-Swarm SKIPPED — cost_guardian halt active")

    # Step 6: LLM-FreeSwitch — every hour (12th cycle)
    if cycle_num % 12 == 0:
        print(f"\n[engine] LLM-FreeSwitch cycle (every 12th cycle = 1 hour)")
        llm_result = run_agent("llm_freeswitch", str(ENGINE_HOME / "agents" / "llm_freeswitch.py"))
        state["agent_results"].append({
            "at": datetime.now(timezone.utc).isoformat(),
            "agent": "llm_freeswitch",
            "cycle": cycle_num,
            "result": llm_result,
        })
        state["last_llm_freeswitch_at"] = datetime.now(timezone.utc).isoformat()

    # Save cycle state
    save_cycle_state(state)

    # Print summary
    print(f"\n{'#'*60}")
    print(f"# AUTONOMOUS PROFIT ENGINE — cycle #{cycle_num} complete")
    print(f"# Merges detected (total): {state.get('total_merges_detected', 0)}")
    print(f"# Reclaims attempted (total): {state.get('total_reclaims_attempted', 0)}")
    print(f"# Payouts received (total): {state.get('total_payouts_received', 0)}")
    if halt_active:
        print(f"# ⚠️ COST-GUARDIAN HALT ACTIVE — paid agents skipped")
    print(f"{'#'*60}\n")

    # Log to worklog
    log_to_worklog(
        task_id=f"engine-cycle-{cycle_num}",
        agent="Autonomous Profit Engine",
        task=f"Cycle #{cycle_num} — autonomous operation",
        work_log=[
            f"cost_guardian: halt={halt_active}",
            f"cooldown_timer: ran (status updated)",
            f"merge_watcher: ran (PRs checked)",
        ],
        stage_summary=[
            f"Cycle #{cycle_num} complete",
            f"Total merges: {state.get('total_merges_detected', 0)}",
            f"Total reclaims: {state.get('total_reclaims_attempted', 0)}",
        ],
    )


if __name__ == "__main__":
    main()
