#!/usr/bin/env python3
"""
PC Bot 24/7 — runs locally on Windows.
Monitors GitHub PRs, Frantic, wallet, email.
Auto-claims bounties, opens browser when action needed.

NO remote access. NO tunnels. NO open ports.
All actions logged to bot.log on Desktop.
"""
import json, os, time, subprocess, webbrowser, urllib.request, urllib.error, sys
from datetime import datetime
from pathlib import Path

# Config — stored in env or hardcoded
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "YOUR_GITHUB_TOKEN_HERE")
REDDIT_USER = "makar52nn"
REDDIT_PASS = "5841052Nn@"
WALLET_BASE = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
XLM_WALLET = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
FRANTIC_AGENT = "agent-b94b60"
BTC_WALLET = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"

# Log file on Desktop
LOG_FILE = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")) + r"\Desktop\bot.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def github_api(url, method="GET", data=None):
    """Call GitHub API with our token."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "pc-bot-247"
    }
    if data:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)[:100]}

def check_prs():
    """Check all our open PRs for merges/comments."""
    prs = [
        ("Ikalus1988/MisakaNet", 2921),
        ("GermanoDevelopment/greenfield", 51),
        ("GermanoDevelopment/greenfield", 52),
        ("Heliobond/frontend", 676),
        ("IfcOpenShell/IfcOpenShell", 9855),
    ]
    for repo, num in prs:
        result = github_api(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if result.get("merged"):
            log(f"💰 MERGED! {repo}#{num} — {result.get('title','?')[:60]}")
            # Check for payment
            webbrowser.open(f"https://github.com/{repo}/pull/{num}")
        elif result.get("state") == "closed" and not result.get("merged"):
            log(f"❌ CLOSED (not merged): {repo}#{num}")
        else:
            comments = result.get("comments", 0)
            updated = result.get("updated_at", "?")[:19]
            log(f"⏳ {repo}#{num}: open ({comments}c, updated {updated})")
        
        # Check for new comments
        comments = github_api(f"https://api.github.com/repos/{repo}/issues/{num}/comments?per_page=1&sort=created&direction=desc")
        if isinstance(comments, list) and comments:
            last_comment = comments[0]
            user = last_comment.get("user", {}).get("login", "?")
            created = last_comment.get("created_at", "?")[:19]
            body = last_comment.get("body", "")[:100]
            if "makar52nn" not in user and "github-actions" not in user and "bot" not in user.lower():
                log(f"💬 NEW COMMENT on {repo}#{num} by @{user}: {body}")
                webbrowser.open(f"https://github.com/{repo}/pull/{num}")

def check_frantic():
    """Check Frantic agent status for payout."""
    try:
        req = urllib.request.Request(f"https://gofrantic.com/v1/agents/{FRANTIC_AGENT}/status")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        earned = d.get("agent", {}).get("earnedUsd", 0)
        opens = d.get("work", {}).get("open", [])
        stage = opens[0].get("stage", "?") if opens else "none"
        if earned > 0:
            log(f"💰 FRANTIC PAID! ${earned}! Stage: {stage}")
            webbrowser.open("https://gofrantic.com/a/agent-b94b60")
        else:
            log(f"🤖 Frantic: ${earned} earned, stage: {stage}")
    except Exception as e:
        log(f"⚠️ Frantic check failed: {str(e)[:50]}")

def check_wallet():
    """Check ETH balance on Base."""
    try:
        data = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [WALLET_BASE, "latest"],
            "id": 1
        }).encode()
        req = urllib.request.Request(
            "https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
        bal = int(result.get("result", "0x0"), 16) / 1e18
        usd = bal * 2700
        if usd > 1.5:  # More than expected — possible incoming payment!
            log(f"💰 WALLET INCREASED! {bal:.6f} ETH (${usd:.2f})")
            webbrowser.open(f"https://basescan.org/address/{WALLET_BASE}")
        else:
            log(f"💵 Wallet: {bal:.6f} ETH (${usd:.2f})")
    except Exception as e:
        log(f"⚠️ Wallet check failed: {str(e)[:50]}")

def check_email():
    """Check for new GitHub notifications via API."""
    result = github_api("https://api.github.com/notifications?per_page=5")
    if isinstance(result, list):
        unread = [n for n in result if n.get("unread")]
        for n in unread:
            subj = n.get("subject", {})
            title = subj.get("title", "?")[:60]
            repo = n.get("repository", {}).get("full_name", "?")
            reason = n.get("reason", "?")
            if reason in ["mention", "assign", "review_requested"]:
                log(f"📧 NOTIFICATION [{reason}]: {repo}: {title}")
                url = n.get("subject", {}).get("url", "")
                if url:
                    # Open in browser
                    html_url = url.replace("api.github.com/repos", "github.com").replace("/issues/", "/pull/")
                    webbrowser.open(html_url)
        # Mark as read
        github_api("https://api.github.com/notifications", method="PUT")
    elif isinstance(result, dict) and result.get("error"):
        log(f"⚠️ Email check failed: {result.get('error')}")

def check_new_bounties():
    """Search for new funded bounties with low competition."""
    result = github_api(
        "https://api.github.com/search/issues?q=bounty+state%3Aopen+type%3Aissue+created%3A%3E" + 
        datetime.now().strftime("%Y-%m-%d") + "T00:00:00Z&sort=created&order=desc&per_page=5"
    )
    if isinstance(result, dict):
        items = result.get("items", [])
        for item in items:
            if item.get("comments", 99) <= 2:
                title = item.get("title", "")[:60]
                repo = item.get("repository_url", "").split("/")[-1]
                url = item.get("html_url", "")
                log(f"🎯 NEW BOUNTY [{item.get('comments',0)}c]: {repo}: {title}")
                log(f"   {url}")

def run_cycle():
    """One monitoring cycle."""
    log("=" * 50)
    check_prs()
    check_frantic()
    check_wallet()
    check_email()
    check_new_bounties()
    log("Cycle complete. Sleeping 5 min...")
    log("=" * 50)

def main():
    log("🤖 PC Bot 24/7 STARTED")
    log(f"Wallet: {WALLET_BASE}")
    log(f"Frantic: {FRANTIC_AGENT}")
    log(f"Log file: {LOG_FILE}")
    log("")
    
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Bot stopped by user.")
            break
        except Exception as e:
            log(f"⚠️ Cycle error: {str(e)[:100]}")
        
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
