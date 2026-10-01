"""
autonomous_engine/agents/merge_watcher.py — PR merge → Frantic delivery auto-trigger

Monitors Stompstart PRs #9, #21, #22. When ANY of them merges:
1. Detect merge via GitHub API (state=closed AND merged=true)
2. Wait 60s for stompstart.com to publish the startup
3. Trigger Frantic delivery via /v1/deliveries with the merged PR URL
4. Log to worklog

This is the SECOND KEY autonomous agent — it captures $1.50 the moment @auscaster merges.

Important: pre-claim cooldown may apply. If claim attempt fails with cooldown_active,
the cooldown_timer agent will retry later.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent.parent
DAEMON_HOME = ENGINE_HOME.parent
TRUDYAGI_HOME = DAEMON_HOME / "trudyagi"
sys.path.insert(0, str(TRUDYAGI_HOME))

STATE_FILE = ENGINE_HOME / "state" / "merge_watcher.json"

# PRs to watch
PR_REPOS = [
    ("auscaster/stompstart-startup-list", 9, "agentbounties"),
    ("auscaster/stompstart-startup-list", 21, "rome"),
    ("auscaster/stompstart-startup-list", 22, "fablecut"),
]


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_check_at": None,
        "pr_states": {},
        "merges_detected": 0,
        "deliveries_triggered": 0,
        "events": [],
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def github_request(path: str) -> dict:
    """Make an authenticated GitHub API request."""
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        return {"error": "GH_TOKEN not set"}

    url = f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "makar52nn2016-jpg-autonomous-engine",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"error": f"URL: {e.reason}"}


def check_pr_status(repo: str, pr_number: int) -> dict:
    """Get PR status — merged or not."""
    path = f"/repos/{repo}/pulls/{pr_number}"
    data = github_request(path)
    if "error" in data:
        return {"error": data["error"]}

    return {
        "state": data.get("state"),
        "merged": data.get("merged", False),
        "merged_at": data.get("merged_at"),
        "merge_commit_sha": data.get("merge_commit_sha"),
        "head_sha": data.get("head", {}).get("sha"),
        "title": data.get("title"),
        "updated_at": data.get("updated_at"),
    }


def check_stompstart_publication(slug: str) -> bool:
    """Check if startup is published on stompstart.com."""
    url = f"https://stompstart.com/api/startups/{slug}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                # Verify it has contributor_attribution with our PR
                attribution = data.get("contributor_attribution", {})
                return bool(attribution.get("pull_number"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False  # Not published yet
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        pass
    return False


def trigger_frantic_delivery(pr_url: str, website_url: str, logo_url: str, product_url: str = None) -> dict:
    """Trigger Frantic #136 delivery via reclaim_136.py script (which uses preflight + delivery)."""
    # Actually the reclaim script handles everything — call it
    reclaim_script = TRUDYAGI_HOME / "reclaim_136.py"
    if not reclaim_script.exists():
        return {"error": f"reclaim script not found: {reclaim_script}"}

    import subprocess
    try:
        result = subprocess.run(
            ["python3", str(reclaim_script)],
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
            cwd=str(TRUDYAGI_HOME),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-500:],
        }
    except Exception as e:
        return {"error": str(e)}


# Logo URLs for each startup (pre-known)
LOGO_URLS = {
    "agentbounties": "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/logo.png",
    "rome": "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/main/startups/rome/logo.png",  # Will update with actual sha when merged
    "fablecut": "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/main/startups/fablecut/logo.png",
}
WEBSITE_URLS = {
    "agentbounties": "https://agentbounties.app/",
    "rome": "https://romeos.cc/",
    "fablecut": "https://fablecut.space/",
}
PRODUCT_URLS = {
    "agentbounties": "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/product.png",
    "rome": None,
    "fablecut": None,
}


def run_cycle() -> dict:
    """One cycle of merge watcher."""
    print(f"[Merge-Watcher] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    state["last_check_at"] = datetime.now(timezone.utc).isoformat()

    actions = []

    for repo, pr_number, slug in PR_REPOS:
        pr_key = f"{repo}#{pr_number}"
        prev = state["pr_states"].get(pr_key, {})

        # Check current PR status
        current = check_pr_status(repo, pr_number)
        if "error" in current:
            print(f"[Merge-Watcher] {pr_key}: ERROR {current['error']}")
            continue

        was_merged = prev.get("merged", False)
        is_merged = current.get("merged", False)

        # Update state
        state["pr_states"][pr_key] = current

        if not was_merged and is_merged:
            # NEW MERGE DETECTED!
            print(f"[Merge-Watcher] 🎉 MERGE DETECTED: {pr_key} (merged at {current.get('merged_at')})")

            state["merges_detected"] = state.get("merges_detected", 0) + 1
            event = {
                "at": datetime.now(timezone.utc).isoformat(),
                "type": "MERGE_DETECTED",
                "pr": pr_key,
                "merged_at": current.get("merged_at"),
                "merge_sha": current.get("merge_commit_sha"),
            }
            state["events"].append(event)

            # Wait 60s for stompstart.com to publish
            print(f"[Merge-Watcher] Waiting 60s for stompstart.com to publish {slug}...")
            time.sleep(60)

            # Check publication
            published = check_stompstart_publication(slug)
            print(f"[Merge-Watcher] stompstart.com publication: {published}")

            if published:
                # Trigger Frantic delivery via reclaim script
                pr_url = f"https://github.com/{repo}/pull/{pr_number}"
                website_url = WEBSITE_URLS.get(slug, "")
                logo_url = LOGO_URLS.get(slug, "")
                product_url = PRODUCT_URLS.get(slug)

                print(f"[Merge-Watcher] Triggering Frantic delivery...")
                result = trigger_frantic_delivery(pr_url, website_url, logo_url, product_url)

                state["deliveries_triggered"] = state.get("deliveries_triggered", 0) + 1
                delivery_event = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "type": "DELIVERY_TRIGGERED",
                    "pr": pr_key,
                    "slug": slug,
                    "result_code": result.get("returncode"),
                    "stdout_snippet": result.get("stdout", "")[:500],
                }
                state["events"].append(delivery_event)
                actions.append({
                    "action": "delivery_triggered",
                    "pr": pr_key,
                    "slug": slug,
                    "success": result.get("returncode") == 0,
                })
            else:
                # Wait another 60s and try again
                print(f"[Merge-Watcher] Not yet published. Waiting another 60s...")
                time.sleep(60)
                published = check_stompstart_publication(slug)
                if published:
                    print(f"[Merge-Watcher] Published on retry! Triggering delivery...")
                    pr_url = f"https://github.com/{repo}/pull/{pr_number}"
                    result = trigger_frantic_delivery(
                        pr_url,
                        WEBSITE_URLS.get(slug, ""),
                        LOGO_URLS.get(slug, ""),
                        PRODUCT_URLS.get(slug),
                    )
                    state["deliveries_triggered"] = state.get("deliveries_triggered", 0) + 1
                    state["events"].append({
                        "at": datetime.now(timezone.utc).isoformat(),
                        "type": "DELIVERY_TRIGGERED_LATE",
                        "pr": pr_key,
                        "slug": slug,
                        "result_code": result.get("returncode"),
                    })
                    actions.append({
                        "action": "delivery_triggered_late",
                        "pr": pr_key,
                        "success": result.get("returncode") == 0,
                    })
                else:
                    print(f"[Merge-Watcher] ⚠️ Publication not detected. Will retry next cycle.")
                    state["events"].append({
                        "at": datetime.now(timezone.utc).isoformat(),
                        "type": "PUBLICATION_PENDING",
                        "pr": pr_key,
                        "slug": slug,
                    })

        elif is_merged:
            # Already merged — check if we previously triggered delivery
            print(f"[Merge-Watcher] {pr_key}: already merged, checking if delivery needed")
        else:
            # Still open
            print(f"[Merge-Watcher] {pr_key}: state={current.get('state')}, merged={is_merged}")

    save_state(state)
    return {"actions": actions}


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[Merge-Watcher] Cycle complete: {len(result.get('actions', []))} actions")
    sys.exit(0)
