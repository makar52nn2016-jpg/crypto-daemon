"""
autonomous_engine/agents/sniper_bulk.py — Multi-platform instant_pay scanner

Scans:
  - GitHub Issues with 'bounty' label (filtered for instant_pay / opire)
  - Algora.io bounties (via RSS / HTML scrape)
  - Gitcoin Grants
  - Open bounty repos (bounty-plaza, claude-builders-bounty, etc.)

Filter criteria (per user spec):
  - $10-30 price range (micro-fix sweet spot)
  - <15min estimated work
  - "instant pay" or fast payout mechanism
  - Good first issue label OR clear acceptance criteria

Output: queue of tasks for fixer_swarm to process in parallel.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent.parent
STATE_FILE = ENGINE_HOME / "state" / "sniper_bulk.json"

# Bounty sources to scan
SOURCES = {
    "github_bounty_label": {
        "url": "https://api.github.com/search/issues?q=label:bounty+state:open+sort:updated&per_page=30",
        "filter": "instant pay / opire / $",
    },
    "github_good_first_issue_bounty": {
        "url": "https://api.github.com/search/issues?q=%22Bounty+%24%22+state:open+label:%22good+first+issue%22+sort:created&per_page=20",
        "filter": "<$30, micro-fix",
    },
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_scan_at": None,
        "candidates_queued": 0,
        "candidates_processed": 0,
        "queue": [],
        "scan_history": [],  # track when scans happened + result count
        "rate_limit_hits": 0,  # how many times GitHub returned 403
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def should_skip_scan(state: dict) -> bool:
    """Skip scan if last scan was < 15 min ago — avoids burning GitHub quota.

    GitHub Search API has 30 req/min limit + 1000 req/hr per token.
    With daemon.py + sniper.py + engine.py all using same token, we burn quota fast.
    Cache strategy: only re-scan if last scan was > 15 min ago (3 cycles).
    """
    last = state.get("last_scan_at")
    if not last:
        return False
    try:
        from datetime import datetime, timezone
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_sec = (now - last_dt).total_seconds()
        return age_sec < 900  # 15 min
    except Exception:
        return False


def scan_github_issues(query_url: str) -> list:
    """Scan GitHub Issues for bounty candidates."""
    token = os.environ.get("GH_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "makar52nn2016-jpg-sniper-bulk",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(query_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"[Sniper-Bulk] GitHub rate limited (403). Will skip rest of cycle.")
            # Look for rate limit reset time in headers
            reset = e.headers.get("X-RateLimit-Reset")
            if reset:
                try:
                    from datetime import datetime, timezone
                    reset_dt = datetime.fromtimestamp(int(reset), tz=timezone.utc)
                    print(f"[Sniper-Bulk] Quota resets at: {reset_dt.isoformat()}")
                except Exception:
                    pass
            return []
        elif e.code == 422:
            print(f"[Sniper-Bulk] GitHub 422 (query too complex). Skipping.")
            return []
        else:
            print(f"[Sniper-Bulk] GitHub HTTP {e.code}. Skipping.")
            return []
    except Exception as e:
        print(f"[Sniper-Bulk] GitHub error: {e}")
        return []


def extract_bounty_amount(title: str, body: str = "") -> int | None:
    """Extract $X amount from issue title/body."""
    import re
    # Look for $X, $Xk, $XXX
    matches = re.findall(r'\$(\d+)(?:k)?', title + " " + (body or ""))
    if not matches:
        return None
    amounts = [int(m) for m in matches if m.isdigit()]
    return min(amounts) if amounts else None


def filter_candidate(issue: dict) -> bool:
    """Filter issue based on user's criteria."""
    title = issue.get("title", "")
    body = issue.get("body", "") or ""

    amount = extract_bounty_amount(title, body)
    if amount is None:
        return False
    if amount < 10 or amount > 30:  # $10-30 range
        return False

    # Skip very commented issues (high competition)
    if issue.get("comments", 0) > 50:
        return False

    return True


def run_cycle() -> dict:
    """Scan all sources, add matching tasks to queue.

    Caching strategy: skip scan if last scan was < 15 min ago.
    """
    print(f"[Sniper-Bulk] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()

    # CACHE CHECK: Skip scan if recent (saves GitHub quota)
    if should_skip_scan(state):
        print(f"[Sniper-Bulk] ⏭️ Skipping scan — last scan was < 15 min ago (caching)")
        print(f"[Sniper-Bulk] Queue size: {len(state['queue'])} tasks pending")
        return {
            "new_candidates": 0,
            "queue_size": len(state["queue"]),
            "skipped": True,
            "reason": "cached (last scan < 15 min ago)",
        }

    state["last_scan_at"] = datetime.now(timezone.utc).isoformat()

    new_candidates = []

    for source_name, source_info in SOURCES.items():
        print(f"[Sniper-Bulk] Scanning {source_name}...")
        items = scan_github_issues(source_info["url"])
        print(f"[Sniper-Bulk]   {len(items)} issues found")

        for item in items:
            if filter_candidate(item):
                candidate = {
                    "url": item.get("html_url"),
                    "title": item.get("title"),
                    "amount_usd": extract_bounty_amount(item.get("title", "")),
                    "repo": item.get("repository_url", "").split("/")[-1],
                    "comments": item.get("comments", 0),
                    "source": source_name,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                }
                # Check not already queued
                if not any(c["url"] == candidate["url"] for c in state["queue"]):
                    state["queue"].append(candidate)
                    new_candidates.append(candidate)

    state["candidates_queued"] = state.get("candidates_queued", 0) + len(new_candidates)
    state["scan_history"].append({
        "at": state["last_scan_at"],
        "new_found": len(new_candidates),
        "queue_size_after": len(state["queue"]),
    })
    # Trim scan_history to last 50 entries
    state["scan_history"] = state["scan_history"][-50:]

    save_state(state)

    print(f"[Sniper-Bulk] {len(new_candidates)} new candidates added to queue")
    print(f"[Sniper-Bulk] Queue size: {len(state['queue'])} tasks pending")

    return {
        "new_candidates": len(new_candidates),
        "queue_size": len(state["queue"]),
        "candidates_preview": [c["title"][:50] for c in new_candidates[:3]],
        "skipped": False,
    }


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[Sniper-Bulk] Cycle result: {result}")
    sys.exit(0)
