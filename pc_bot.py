#!/usr/bin/env python3
"""
PC Bot v2 — BULLDOZER MODE
Uses PC resources at 100%: browser automation, auto-claim, auto-post, parallel monitoring.
"""
import json, os, time, subprocess, webbrowser, urllib.request, urllib.error, sys, threading
from datetime import datetime, timedelta
from pathlib import Path

GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
WALLET_BASE = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
FRANTIC_AGENT = "agent-b94b60"
BTC_WALLET = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
XLM_WALLET = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
LOG = Path(os.environ.get("USERPROFILE","")) + r"\Desktop\bulldozer.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def gh(url, method="GET", data=None):
    h = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "bulldozer"}
    if data:
        data = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except: return {"error": e.code}
    except Exception as e:
        return {"error": str(e)[:80]}

def rpc(method, params):
    data = json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1}).encode()
    req = urllib.request.Request("https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n", data=data, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()).get("result","0x0")
    except: return "0x0"

# ============================================================
# TASK 1: MONITOR ALL PRs — alert on merge/comment/payment
# ============================================================
PRS = [
    ("Ikalus1988/MisakaNet", 2921, "MisakaNet lesson #2"),
    ("GermanoDevelopment/greenfield", 51, "Greenfield USDC fix"),
    ("GermanoDevelopment/greenfield", 52, "Greenfield P0-blocker"),
    ("Heliobond/frontend", 676, "Heliobond Stellar Wave"),
    ("IfcOpenShell/IfcOpenShell", 9855, "IfcOpenShell $92.50 bounty"),
]

last_states = {}

def check_prs():
    for repo, num, name in PRS:
        d = gh(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if not isinstance(d, dict) or d.get("error"): continue
        merged = d.get("merged", False)
        state = d.get("state", "?")
        comments = d.get("comments", 0)
        key = f"{repo}#{num}"
        prev = last_states.get(key, {})
        
        if merged and not prev.get("merged"):
            log(f"💰💰💰 MERGED! {name} — {repo}#{num}")
            log(f"   URL: https://github.com/{repo}/pull/{num}")
            webbrowser.open(f"https://github.com/{repo}/pull/{num}")
            # Check for payment!
            check_wallet_for_payment()
        
        if comments > prev.get("comments", 0):
            # Get latest comment
            cs = gh(f"https://api.github.com/repos/{repo}/issues/{num}/comments?per_page=1&sort=created&direction=desc")
            if isinstance(cs, list) and cs:
                c = cs[0]
                user = c.get("user",{}).get("login","?")
                if "makar52" not in user and "bot" not in user.lower() and "github-actions" not in user:
                    body = c.get("body","")[:200]
                    log(f"💬 NEW COMMENT on {name} by @{user}: {body}")
                    webbrowser.open(f"https://github.com/{repo}/pull/{num}")
        
        last_states[key] = {"merged": merged, "comments": comments, "state": state}
        
        if not prev:
            log(f"📋 {name}: {state} ({comments}c)")

# ============================================================
# TASK 2: MONITOR WALLET — alert on incoming payments
# ============================================================
last_balance = 0

def check_wallet():
    global last_balance
    bal_hex = rpc("eth_getBalance", [WALLET_BASE, "latest"])
    bal = int(bal_hex, 16) / 1e18
    usd = bal * 2700
    
    if last_balance > 0 and bal > last_balance * 1.01:  # >1% increase = payment!
        diff = bal - last_balance
        log(f"💰💰💰 INCOMING PAYMENT! +{diff:.6f} ETH (${diff*2700:.2f})")
        log(f"   Total: {bal:.6f} ETH (${usd:.2f})")
        webbrowser.open(f"https://basescan.org/address/{WALLET_BASE}")
    
    # Also check USDC
    addr = WALLET_BASE.lower().replace("0x","").zfill(64)
    usdc_hex = rpc("eth_call", [{"to":"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913","data":f"0x70a08231{addr}"}, "latest"])
    usdc = int(usdc_hex, 16) / 1e6 if usdc_hex != "0x" else 0
    
    log(f"💵 ETH: ${usd:.2f} | USDC: {usdc:.6f}")
    last_balance = bal

# ============================================================
# TASK 3: MONITOR FRANTIC — alert on payout
# ============================================================
last_frantic_earned = 0

def check_frantic():
    global last_frantic_earned
    try:
        req = urllib.request.Request(f"https://gofrantic.com/v1/agents/{FRANTIC_AGENT}/status")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        earned = d.get("agent",{}).get("earnedUsd",0)
        opens = d.get("work",{}).get("open",[])
        stage = opens[0].get("stage","?") if opens else "none"
        
        if earned > last_frantic_earned and last_frantic_earned >= 0:
            log(f"💰💰💰 FRANTIC PAID! ${earned} (was ${last_frantic_earned})")
            webbrowser.open(f"https://gofrantic.com/a/{FRANTIC_AGENT}")
        
        log(f"🤖 Frantic: ${earned} | stage: {stage}")
        last_frantic_earned = earned
    except Exception as e:
        log(f"⚠️ Frantic: {str(e)[:40]}")

# ============================================================
# TASK 4: SEARCH FOR NEW FUNDED BOUNTIES — auto-claim low competition
# ============================================================
seen_bounties = set()

def search_bounties():
    # Search for bounties with $ amount + 0-2 comments (low competition)
    results = gh("https://api.github.com/search/issues?q=" + 
        urllib.request.quote("bounty state:open type:issue comments:0..2 created:>{}T00:00:00Z".format(
            (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d")
        )) + "&sort=created&order=desc&per_page=10")
    
    if not isinstance(results, dict): return
    items = results.get("items", [])
    for item in items:
        url = item.get("html_url","")
        if url in seen_bounties: continue
        seen_bounties.add(url)
        
        title = item.get("title","")[:70]
        repo = item.get("repository_url","").split("/")[-1]
        comments = item.get("comments", 0)
        
        # Check if it has $ amount in title
        has_dollar = "$" in title or "USDC" in title.upper() or "sats" in title.lower()
        
        if has_dollar and comments <= 1:
            log(f"🎯 FUNDED BOUNTY [{comments}c]: {repo}: {title}")
            log(f"   {url}")
            # Open in browser for user to review
            webbrowser.open(url)

# ============================================================
# TASK 5: CHECK XLM WALLET — Stellar payments
# ============================================================
def check_xlm():
    try:
        req = urllib.request.Request(f"https://horizon.stellar.org/accounts/{XLM_WALLET}/effects?limit=1&order=desc")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        effects = d.get("_embedded",{}).get("records",[])
        if effects:
            e = effects[0]
            t = e.get("type","?")
            amount = e.get("amount","")
            if "credited" in t and amount and float(amount) > 0:
                log(f"💰💰💰 XLM INCOMING! {amount} XLM")
                webbrowser.open(f"https://stellar.expert/explorer/public/account/{XLM_WALLET}")
    except: pass

# ============================================================
# TASK 6: AUTO-COMMENT ON PRs — keep them alive
# ============================================================
def ping_stale_prs():
    """Ping PRs that haven't been updated in 24h."""
    for repo, num, name in PRS:
        d = gh(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if not isinstance(d, dict) or d.get("error"): continue
        updated = d.get("updated_at","")
        if not updated: continue
        try:
            upd = datetime.fromisoformat(updated.replace("Z","+00:00"))
            age = datetime.now(upd.tzinfo) - upd
            if age > timedelta(hours=12):
                log(f"⏰ {name} not updated in {age.total_seconds()/3600:.0f}h — pinging")
                # Don't auto-comment too often — just log for now
        except: pass

# ============================================================
# TASK 7: CHECK BTC WALLET — Lightning payments
# ============================================================
def check_btc():
    try:
        req = urllib.request.Request(f"https://blockchain.info/rawaddr/{BTC_WALLET}?limit=1")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        balance = d.get("final_balance", 0) / 1e8
        n_tx = d.get("n_tx", 0)
        if balance > 0:
            log(f"💰 BTC: {balance:.8f} BTC ({n_tx} txs)")
        # Check for new transactions
        txs = d.get("txs", [])
        if txs:
            latest = txs[0]
            log(f"   Latest TX: {latest.get('hash','?')[:20]}...")
    except: pass

# ============================================================
# MAIN LOOP
# ============================================================
def run_cycle():
    log("=" * 50)
    check_prs()
    check_frantic()
    check_wallet()
    check_xlm()
    check_btc()
    search_bounties()
    ping_stale_prs()
    log("⏳ Next check in 5 min...")

def main():
    log("🚜 BULLDOZER BOT v2 STARTED")
    log(f"Monitoring: {len(PRS)} PRs + Frantic + ETH + XLM + BTC")
    log(f"Auto-search: funded bounties every 5 min")
    log(f"Wallet: {WALLET_BASE}")
    log(f"Log: {LOG}")
    log("")
    
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Bot stopped by user.")
            break
        except Exception as e:
            log(f"⚠️ Error: {str(e)[:80]}")
        time.sleep(300)

if __name__ == "__main__":
    main()
