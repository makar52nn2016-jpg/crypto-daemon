"""
autonomous_engine/agents/cooldown_timer.py — Frantic cooldown tracker

Monitors Frantic #136 claim cooldown. When claim expires (or about to expire),
automatically executes the re-claim script and triggers Frantic delivery.

This is the KEY autonomous agent — it captures $1.50 USDC the moment cooldown ends,
no human intervention needed.

Flow:
    1. Check Frantic API for current claim status
    2. If claim expired AND cooldown_active → calculate retry_after_seconds
    3. If cooldown_active AND retry_after_seconds < 60 → prepare re-claim payload
    4. If cooldown NOT active → execute re-claim immediately
    5. Log to worklog with timestamp + result
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# Engine paths (relative to crypto-daemon/)
ENGINE_HOME = Path(__file__).resolve().parent.parent
DAEMON_HOME = ENGINE_HOME.parent  # crypto-daemon/
TRUDYAGI_HOME = DAEMON_HOME / "trudyagi"

# Add trudyagi to path for worklog import
sys.path.insert(0, str(TRUDYAGI_HOME))

# State file path
STATE_FILE = ENGINE_HOME / "state" / "cooldown_timer.json"

# Frantic API
FRANTIC_BASE = "https://gofrantic.com"
AGENT_KID = "agent-b94b60"
BOUNTY_NUMBER = 136


def load_state() -> dict:
    """Load or initialize cooldown timer state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_check_at": None,
        "claim_status": None,
        "retry_after_seconds": None,
        "cooldown_ends_at": None,
        "reclaim_attempts": 0,
        "successful_reclaims": 0,
        "failed_reclaims": 0,
        "events": [],
    }


def save_state(state: dict) -> None:
    """Save state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def frantic_request(method: str, path: str, data: dict = None) -> dict:
    """Make a Frantic API request."""
    agent_token = os.environ.get("FRANTIC_AGENT_TOKEN", "")
    if not agent_token:
        return {"error": "FRANTIC_AGENT_TOKEN not set"}

    url = f"{FRANTIC_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {agent_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"error": f"URL: {e.reason}"}


def check_claim_status() -> dict:
    """Check current Frantic #136 claim status via /v1/board."""
    resp = frantic_request("GET", "/v1/agents/agent-b94b60/status")
    agent = resp.get("agent", {})
    latest_event = agent.get("latestEvent", {})

    # Also check bounty #136 to see claim_progress
    bounty_resp = frantic_request("GET", "/v1/bounties/136")
    bounty = bounty_resp.get("bounty", {})
    claim_progress = bounty.get("claim_progress", {})

    return {
        "agent_latest_event": latest_event,
        "claim_progress": claim_progress,
        "agent_eligible": agent.get("eligible", False),
        "paid_bounties": agent.get("paidBounties", 0),
        "earned_usd": agent.get("earnedUsd", 0),
    }


def attempt_reclaim() -> dict:
    """Execute the re-claim script."""
    reclaim_script = TRUDYAGI_HOME / "reclaim_136.py"
    if not reclaim_script.exists():
        return {"error": f"Reclaim script not found: {reclaim_script}"}

    try:
        # Run reclaim script with same env vars
        env = os.environ.copy()
        result = subprocess.run(
            ["python3", str(reclaim_script)],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=str(TRUDYAGI_HOME),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"error": "Reclaim script timed out (120s)"}
    except Exception as e:
        return {"error": str(e)}


def run_cycle() -> dict:
    """One cycle of cooldown timer.

    Returns dict with cycle result.
    """
    print(f"[Cooldown-Timer] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    state["last_check_at"] = datetime.now(timezone.utc).isoformat()

    # Step 1: Check current Frantic status
    status = check_claim_status()
    latest = status.get("agent_latest_event", {})

    # Parse cooldown from latest event text
    # Example: "#136 · claim expired" or "#130 · claim expired"
    event_text = latest.get("text", "")
    event_kind = latest.get("kind", "")

    # Check if we have an active claim by looking at recent events
    # If latest event is REOPENED (claim expired) → check cooldown
    # If latest event is CLAIMED/DELIVERED → check claim_id from event ref

    claim_progress = status.get("claim_progress", {})
    active_claims = claim_progress.get("active", 0)
    delivered = claim_progress.get("delivered", 0)
    accepted = claim_progress.get("accepted", 0)
    paid = claim_progress.get("paid", 0)

    print(f"[Cooldown-Timer] Frantic #136: active={active_claims}, delivered={delivered}, accepted={accepted}, paid={paid}")
    print(f"[Cooldown-Timer] Agent earned: ${status.get('earned_usd', 0)}, paid_bounties: {status.get('paid_bounties', 0)}")
    print(f"[Cooldown-Timer] Latest event: {event_kind} - {event_text[:80]}")

    # If MY paid_bounties > 0 → SUCCESS! (Check personal agent stats, NOT bounty-wide paid count)
    # The bounty.claim_progress.paid field shows TOTAL payouts to ALL agents — not just me.
    # I need to check agent.paidBounties (my personal count) instead.
    my_paid_bounties = status.get("paid_bounties", 0)
    my_earned_usd = status.get("earned_usd", 0)
    if my_paid_bounties > 0 or my_earned_usd > 0:
        event = {
            "at": datetime.now(timezone.utc).isoformat(),
            "type": "PAYOUT_RECEIVED",
            "details": f"Frantic #136 paid. My earned: ${my_earned_usd}, paid_bounties: {my_paid_bounties}",
        }
        state["events"].append(event)
        state["successful_reclaims"] = state.get("successful_reclaims", 0) + 1
        save_state(state)
        print(f"[Cooldown-Timer] 🎉 PAYOUT DETECTED! Earned: ${my_earned_usd}")
        return {"action": "payout_detected", "amount_usd": my_earned_usd, "status": status}

    # Also log bounty-wide activity (other agents getting paid)
    if paid > 0:
        print(f"[Cooldown-Timer] ℹ️ Bounty #136 has {paid} total payouts to OTHER agents (not me yet)")
        print(f"[Cooldown-Timer]    That means {paid} startups have been published on Stompstart")

    # If active_claims > 0 → my claim is alive, just wait
    if active_claims > 0 and "claim expired" not in event_text.lower():
        state["claim_status"] = "active"
        state["cooldown_ends_at"] = None
        save_state(state)
        print(f"[Cooldown-Timer] Claim still active. Waiting for review.")
        return {"action": "wait_active_claim", "status": status}

    # If latest event says "claim expired" → check if we can re-claim now
    if "claim expired" in event_text.lower() or event_kind == "REOPENED":
        # Try to re-claim immediately
        print(f"[Cooldown-Timer] ⏰ Claim expired! Attempting re-claim...")
        state["reclaim_attempts"] = state.get("reclaim_attempts", 0) + 1

        reclaim_result = attempt_reclaim()
        event = {
            "at": datetime.now(timezone.utc).isoformat(),
            "type": "RECLAIM_ATTEMPT",
            "result": "success" if reclaim_result.get("returncode") == 0 else "failed",
            "details": reclaim_result.get("stdout", "")[:500] if reclaim_result.get("returncode") == 0 else reclaim_result.get("error", reclaim_result.get("stderr", ""))[:500],
        }
        state["events"].append(event)

        if reclaim_result.get("returncode") == 0:
            state["successful_reclaims"] = state.get("successful_reclaims", 0) + 1
            state["claim_status"] = "reclaimed"
            print(f"[Cooldown-Timer] ✅ Re-claim script executed successfully")
            save_state(state)
            return {"action": "reclaim_executed", "result": reclaim_result}
        else:
            state["failed_reclaims"] = state.get("failed_reclaims", 0) + 1
            # Check for cooldown_active error
            stdout = reclaim_result.get("stdout", "")
            if "cooldown_active" in stdout:
                # Extract retry_after_seconds
                import re
                match = re.search(r'"retry_after_seconds":\s*(\d+)', stdout)
                if match:
                    retry_after = int(match.group(1))
                    cooldown_ends = datetime.now(timezone.utc).timestamp() + retry_after
                    state["cooldown_ends_at"] = datetime.fromtimestamp(
                        cooldown_ends, tz=timezone.utc
                    ).isoformat()
                    state["claim_status"] = "cooldown_active"
                    state["retry_after_seconds"] = retry_after
                    print(f"[Cooldown-Timer] ⏳ Cooldown active. Ends at {state['cooldown_ends_at']} ({retry_after}s = {retry_after/3600:.1f}h remaining)")

                    # PRE-COMPUTE PAYLOAD: While we wait, prepare the claim payload
                    # so when cooldown ends, we fire instantly without recomputation.
                    state["precomputed_payload"] = {
                        "bounty": BOUNTY_NUMBER,
                        "agent_kid": AGENT_KID,
                        "agent_token_env": "FRANTIC_AGENT_TOKEN",
                        "artifacts": [
                            "pr_url=https://github.com/auscaster/stompstart-startup-list/pull/9",
                            "website_url=https://agentbounties.app/",
                            "logo_url=https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/logo.png",
                            "product_url=https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/product.png",
                        ],
                        "reclaim_script_path": str(TRUDYAGI_HOME / "reclaim_136.py"),
                        "ready_to_fire": True,
                    }
                    print(f"[Cooldown-Timer] 🎯 Pre-computed claim payload — ready to fire instantly when cooldown ends")
                else:
                    state["claim_status"] = "cooldown_active_unknown"
                    print(f"[Cooldown-Timer] ⏳ Cooldown active but no retry_after_seconds in response")
            else:
                state["claim_status"] = "reclaim_failed"
                print(f"[Cooldown-Timer] ❌ Re-claim failed: {reclaim_result.get('stderr', reclaim_result.get('error', 'unknown'))[:200]}")
            save_state(state)
            return {"action": "reclaim_blocked", "result": reclaim_result}

    # Default: just save status
    state["claim_status"] = "unknown"
    save_state(state)
    return {"action": "noop", "status": status}


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[Cooldown-Timer] Cycle result: {result.get('action')}")
    sys.exit(0)
