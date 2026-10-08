#!/usr/bin/env python3
"""
BULLDOZER v3 — Active money digger.
Searches bounties, claims them, monitors email, checks PRs, watches wallet.
Uses PC resources to MAXIMIZE income.
"""
import json, os, time, urllib.request, urllib.error, imaplib, email
from email.header import decode_header
from datetime import datetime, timedelta

GH_TOKEN = os.environ.get("GH_TOKEN", "")
WALLET = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
FRANTIC = "agent-b94b60"
XLM = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
BTC = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
EMAIL = "makar52nn2016@gmail.com"
EMAIL_PASS = "hgxs ozyt zlwg mewr"
LOG = os.path.join(os.environ.get("USERPROFILE",""), "Desktop", "bulldozer.log")

PRS = [
    ("Ikalus1988/MisakaNet", 2921),
    ("GermanoDevelopment/greenfield", 51),
    ("GermanoDevelopment/greenfield", 52),
    ("Heliobond/frontend", 676),
    ("IfcOpenShell/IfcOpenShell", 9855),
    ("vouchlabsio/humanvouch", 113),
]

last_balance = 0
last_frantic = 0
seen_bounties = set()
last_email_count = 0

def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def gh(url, method="GET", data=None):
    h = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "bulldozer"}
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
        return {"error": str(e)[:60]}

# ============================================================
# 1. EMAIL MONITOR — check Gmail for new GitHub/payment emails
# ============================================================
def check_email():
    global last_email_count
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL, EMAIL_PASS)
        mail.select("INBOX")
        typ, data = mail.search(None, "ALL")
        ids = data[0].split()
        total = len(ids)
        
        if total > last_email_count and last_email_count > 0:
            new_count = total - last_email_count
            log(f"📧 {new_count} NEW EMAIL(S)! Total: {total}")
            # Read last 3 new emails
            for mid in reversed(ids[-min(new_count, 3):]):
                typ, msg_data = mail.fetch(mid, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = decode_header(msg.get("Subject",""))
                        st = ""
                        for part, enc in subject:
                            if isinstance(part, bytes):
                                st += part.decode(enc or "utf-8", errors="replace")
                            else:
                                st += part
                        frm = msg.get("From","?")[:40]
                        # Check for important keywords
                        important = any(k in st.lower() for k in ['merge','paid','reward','payout','success','approved','sats','usdc','bounty'])
                        marker = "💰" if important else "  "
                        log(f"  {marker} {frm}: {st[:80]}")
                        # If merge/payment — open browser!
                        if any(k in st.lower() for k in ['merged','paid','reward','payout']):
                            import webbrowser
                            webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
        
        last_email_count = total
        mail.logout()
        log(f"📧 Email: {total} total (last check: {last_email_count})")
    except Exception as e:
        log(f"📧 Email check failed: {str(e)[:50]}")

# ============================================================
# 2. ACTIVE BOUNTY HUNTER — search + auto-claim
# ============================================================
def hunt_bounties():
    """Search for NEW funded bounties with $ + 0 comments. Auto-claim the best ones."""
    # Search for $ bounties with 0 comments created in last 6 hours
    six_hours_ago = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = urllib.request.quote(f'bounty state:open type:issue comments:0 created:>{six_hours_ago}')
    
    results = gh(f"https://api.github.com/search/issues?q={query}&sort=created&order=desc&per_page=10")
    
    if not isinstance(results, dict) or results.get("error"):
        return
    
    items = results.get("items", [])
    found = 0
    for item in items:
        title = item.get("title", "")
        url = item.get("html_url", "")
        
        if url in seen_bounties:
            continue
        seen_bounties.add(url)
        
        # Check for $ amount in title
        has_money = any(s in title for s in ["$", "USDC", "sats", "BTC", "ETH"])
        if not has_money:
            continue
        
        repo = item.get("repository_url", "").split("/")[-1]
        comments = item.get("comments", 0)
        
        if comments == 0 and has_money:
            found += 1
            log(f"🎯 FOUND BOUNTY: {repo}: {title[:60]}")
            log(f"   {url}")
            
            # Open in browser for user to see
            import webbrowser
            webbrowser.open(url)
            
            # DON'T auto-claim — let user decide
            # But log it prominently
    
    if found == 0:
        log(f"🔍 Searched {len(items)} issues — no new funded bounties with 0 comments")
    else:
        log(f"🔍 Found {found} new funded bounties! Opened in browser.")

# ============================================================
# 3. PR MONITOR — check all PRs for merges + new comments
# ============================================================
def check_prs():
    for repo, num in PRS:
        d = gh(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if not isinstance(d, dict) or d.get("error"):
            continue
        
        merged = d.get("merged", False)
        state = d.get("state", "?")
        comments = d.get("comments", 0)
        title = d.get("title", "?")[:40]
        
        if merged:
            log(f"💰💰💰 MERGED! {repo}#{num}: {title}")
            import webbrowser
            webbrowser.open(f"https://github.com/{repo}/pull/{num}")
            # Check wallet for payment!
            check_wallet()
        elif state == "open":
            log(f"📋 {repo}#{num}: open ({comments}c) — {title}")
        else:
            log(f"❌ {repo}#{num}: {state} — {title}")

# ============================================================
# 4. WALLET MONITOR — ETH + USDC on Base
# ============================================================
def check_wallet():
    global last_balance
    try:
        data = json.dumps({"jsonrpc":"2.0","method":"eth_getBalance","params":[WALLET,"latest"],"id":1}).encode()
        req = urllib.request.Request("https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n", data=data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
        bal = int(result.get("result","0x0"), 16) / 1e18
        usd = bal * 2700
        
        if last_balance > 0 and bal > last_balance * 1.01:
            diff = bal - last_balance
            log(f"💰💰💰 PAYMENT RECEIVED! +{diff:.6f} ETH (+${diff*2700:.2f})")
            import webbrowser
            webbrowser.open(f"https://basescan.org/address/{WALLET}")
        
        # Check USDC
        addr = WALLET.lower().replace("0x","").zfill(64)
        usdc_data = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913","data":f"0x70a08231{addr}"}, "latest"],"id":1}).encode()
        usdc_req = urllib.request.Request("https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n", data=usdc_data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(usdc_req, timeout=10) as r:
            usdc_result = json.loads(r.read().decode())
        usdc_bal = int(usdc_result.get("result","0x0"), 16) / 1e6
        
        log(f"💵 ETH: ${usd:.2f} | USDC: {usdc_bal:.6f}")
        last_balance = bal
    except Exception as e:
        log(f"💵 Wallet check failed: {str(e)[:40]}")

# ============================================================
# 5. FRANTIC MONITOR
# ============================================================
def check_frantic():
    global last_frantic
    try:
        req = urllib.request.Request(f"https://gofrantic.com/v1/agents/{FRANTIC}/status")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        earned = d.get("agent",{}).get("earnedUsd",0)
        opens = d.get("work",{}).get("open",[])
        stage = opens[0].get("stage","?") if opens else "none"
        
        if earned > last_frantic and last_frantic >= 0:
            log(f"💰💰💰 FRANTIC PAID! ${earned}!")
            import webbrowser
            webbrowser.open(f"https://gofrantic.com/a/{FRANTIC}")
        
        log(f"🤖 Frantic: ${earned} | {stage}")
        last_frantic = earned
    except Exception as e:
        log(f"🤖 Frantic check failed: {str(e)[:40]}")

# ============================================================
# 6. XLM + BTC CHECK
# ============================================================
def check_xlm_btc():
    try:
        req = urllib.request.Request(f"https://horizon.stellar.org/accounts/{XLM}")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        bal = d.get("balances",[{}])[0].get("balance","0")
        log(f"💎 XLM: {bal}")
    except: pass
    
    try:
        req = urllib.request.Request(f"https://blockchain.info/rawaddr/{BTC}?limit=1")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        bal = d.get("final_balance",0) / 1e8
        n_tx = d.get("n_tx",0)
        if bal > 0 or n_tx > 0:
            log(f"₿ BTC: {bal:.8f} ({n_tx} txs)")
    except: pass

# ============================================================
# MAIN — bulldozer cycle
# ============================================================
def run_cycle():
    log("=" * 60)
    log("🚜 BULLDOZER CYCLE START")
    log("=" * 60)
    
    log("--- 1. Checking email ---")
    check_email()
    
    log("--- 2. Hunting bounties ---")
    hunt_bounties()
    
    log("--- 3. Checking PRs ---")
    check_prs()
    
    log("--- 4. Checking wallet ---")
    check_wallet()
    
    log("--- 5. Checking Frantic ---")
    check_frantic()
    
    log("--- 6. Checking XLM + BTC ---")
    check_xlm_btc()
    
    log("=" * 60)
    log(f"⏳ Cycle done. Sleeping 5 min. Next: {datetime.now() + timedelta(minutes=5):%H:%M:%S}")
    log("=" * 60)

def main():
    log("🚜🚜🚜 BULLDOZER v3 STARTED 🚜🚜🚜")
    log(f"📊 Monitoring: {len(PRS)} PRs + Frantic + ETH + XLM + BTC + Email")
    log(f"🔍 Active bounty hunter: searches every 5 min")
    log(f"📧 Email monitor: checks Gmail for new notifications")
    log(f"💵 Wallet: {WALLET}")
    log(f"📝 Log: {LOG}")
    log("")
    
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Bot stopped by user.")
            break
        except Exception as e:
            log(f"⚠️ Cycle error: {str(e)[:80]}")
        time.sleep(300)

if __name__ == "__main__":
    main()
