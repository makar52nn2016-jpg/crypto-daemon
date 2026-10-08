#!/usr/bin/env python3
"""
BULLDOZER v4 — with LIVE DASHBOARD window.
Opens a second window showing everything the bot does in real-time.
"""
import json, os, time, urllib.request, urllib.error, imaplib, email, sys, threading
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path

# Config
GH_TOKEN = os.environ.get("GH_TOKEN", "")
WALLET = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
FRANTIC = "agent-b94b60"
XLM = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
BTC = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
EMAIL_ADDR = "makar52nn2016@gmail.com"
EMAIL_PASS = "hgxs ozyt zlwg mewr"
LOG = os.path.join(os.environ.get("USERPROFILE",""), "Desktop", "bulldozer.log")

PRS = [
    ("Ikalus1988/MisakaNet", 2921, "MisakaNet lesson #2"),
    ("GermanoDevelopment/greenfield", 51, "Greenfield USDC fix"),
    ("GermanoDevelopment/greenfield", 52, "Greenfield P0-blocker"),
    ("Heliobond/frontend", 676, "Heliobond Stellar Wave"),
    ("IfcOpenShell/IfcOpenShell", 9855, "IfcOpenShell $92.50"),
    ("vouchlabsio/humanvouch", 113, "humanvouch $70"),
]

# ============================================================
# LIVE DASHBOARD — opens a window showing bot activity
# ============================================================
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>🚜 Bulldozer Bot — Live Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0e1a;color:#00ff41;font-family:Consolas,monospace;padding:10px}
.header{font-size:24px;text-align:center;padding:10px;background:#111;color:#00ff41;border:1px solid #222}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin:10px 0}
.stat{background:#111;padding:10px;border:1px solid #222;text-align:center}
.stat .num{font-size:20px;font-weight:bold}
.stat .lbl{font-size:10px;color:#888}
#log{background:#000;border:1px solid #222;height:400px;overflow-y:auto;padding:10px;font-size:12px;line-height:1.6}
.log-entry{padding:2px 0;border-bottom:1px solid #111}
.money{color:#00ff41;font-weight:bold}
.alert{color:#ff4444;font-weight:bold}
.info{color:#5599ff}
.bounty{color:#ffaa00}
.prs{margin:10px 0}
.pr{display:inline-block;margin:3px;padding:4px 8px;border:1px solid #333;border-radius:4px;font-size:11px}
.pr.merged{background:#0a3a0a;color:#00ff41;border-color:#00ff41}
.pr.open{background:#1a1a2a;color:#5599ff}
.pr.closed{background:#3a1a1a;color:#ff4444}
.cycle-bar{background:#111;height:20px;margin:5px 0;border:1px solid #222}
.cycle-fill{background:#00ff41;height:100%;transition:width 1s}
.footer{text-align:center;color:#555;font-size:10px;margin-top:10px}
</style>
</head>
<body>
<div class="header">🚜 BULLDOZER BOT v4 — LIVE DASHBOARD</div>
<div class="stats">
<div class="stat"><div class="num" id="stat-eth">$0.91</div><div class="lbl">ETH BALANCE</div></div>
<div class="stat"><div class="num" id="stat-frantic">$0</div><div class="lbl">FRANTIC EARNED</div></div>
<div class="stat"><div class="num" id="stat-prs">6</div><div class="lbl">ACTIVE PRs</div></div>
<div class="stat"><div class="num" id="stat-earned">$0</div><div class="lbl">TOTAL EARNED</div></div>
</div>
<div class="cycle-bar"><div class="cycle-fill" id="cycle-fill" style="width:0%"></div></div>
<div class="prs" id="pr-list">Loading PRs...</div>
<div id="log">Starting...</div>
<div class="footer">Bot running locally on your PC | No remote access | 24/7</div>
<script>
const log = document.getElementById('log');
const cycleFill = document.getElementById('cycle-fill');

function addLog(text, cls) {
    const div = document.createElement('div');
    div.className = 'log-entry ' + (cls || '');
    div.textContent = text;
    log.insertBefore(div, log.firstChild);
    if (log.children.length > 200) log.removeChild(log.lastChild);
}

function updateStat(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function updatePRs(prs) {
    const el = document.getElementById('pr-list');
    el.innerHTML = '';
    for (const pr of prs) {
        const div = document.createElement('div');
        div.className = 'pr ' + pr.state;
        div.textContent = pr.name + ' (' + pr.comments + 'c)';
        el.appendChild(div);
    }
}

function startCycle() {
    cycleFill.style.width = '0%';
    let pct = 0;
    const interval = setInterval(() => {
        pct += 2;
        cycleFill.style.width = pct + '%';
        if (pct >= 100) { clearInterval(interval); cycleFill.style.width = '100%'; }
    }, 100);
}

// Poll for updates from the bot
async function poll() {
    try {
        const r = await fetch('http://localhost:9876/status');
        const d = await r.json();
        if (d.logs) {
            for (const entry of d.logs) {
                addLog(entry.text, entry.cls);
            }
        }
        if (d.stats) {
            updateStat('stat-eth', d.stats.eth || '$0.91');
            updateStat('stat-frantic', d.stats.frantic || '$0');
            updateStat('stat-prs', d.stats.prs || '6');
            updateStat('stat-earned', d.stats.earned || '$0');
        }
        if (d.prs) updatePRs(d.prs);
        if (d.cycle) startCycle();
    } catch(e) {
        // Bot not responding yet
    }
}

setInterval(poll, 2000);
poll();
</script>
</body>
</html>
"""

# State
last_balance = 0
last_frantic = 0
seen_bounties = set()
last_email_count = 0
bot_logs = []
bot_stats = {"eth": "$0.91", "frantic": "$0", "prs": "6", "earned": "$0"}
bot_prs = []

def log(m, cls=""):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Add to dashboard state
    bot_logs.append({"text": line, "cls": cls})
    if len(bot_logs) > 100:
        bot_logs.pop(0)

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
# DASHBOARD SERVER — serves the HTML + JSON status
# ============================================================
def run_dashboard():
    """Run a tiny HTTP server on port 9876 for the dashboard."""
    import http.server
    
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                # Return JSON status
                data = json.dumps({
                    "logs": bot_logs[-10:],
                    "stats": bot_stats,
                    "prs": bot_prs,
                    "cycle": True
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/" or self.path == "/dashboard":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())
            else:
                self.send_response(404)
                self.end_headers()
        
        def log_message(self, *args):
            pass  # Suppress access logs
    
    server = http.server.HTTPServer(("127.0.0.1", 9876), Handler)
    log("🖥️  Dashboard: http://localhost:9876")
    server.serve_forever()

# ============================================================
# EMAIL MONITOR
# ============================================================
def check_email():
    global last_email_count
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(EMAIL_ADDR, EMAIL_PASS)
        mail.select("INBOX")
        typ, data = mail.search(None, "ALL")
        ids = data[0].split()
        total = len(ids)
        
        if total > last_email_count and last_email_count > 0:
            new_count = total - last_email_count
            log(f"📧 {new_count} NEW EMAIL(S)! Total: {total}", "info")
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
                        important = any(k in st.lower() for k in ['merge','paid','reward','payout','success','sats','usdc','bounty'])
                        marker = "💰" if important else "  "
                        log(f"  {marker} {frm}: {st[:80]}", "money" if important else "info")
                        if any(k in st.lower() for k in ['merged','paid','reward','payout']):
                            import webbrowser
                            webbrowser.open(f"https://mail.google.com/mail/u/0/#inbox")
        else:
            log(f"📧 Email: {total} total — no new", "info")
        
        last_email_count = total
        mail.logout()
    except Exception as e:
        log(f"📧 Email error: {str(e)[:40]}", "alert")

# ============================================================
# BOUNTY HUNTER
# ============================================================
def hunt_bounties():
    six_hours_ago = (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = urllib.request.quote(f'bounty state:open type:issue comments:0 created:>{six_hours_ago}')
    results = gh(f"https://api.github.com/search/issues?q={query}&sort=created&order=desc&per_page=10")
    
    if not isinstance(results, dict) or results.get("error"):
        log(f"🔍 Bounty search failed", "alert")
        return
    
    items = results.get("items", [])
    found = 0
    for item in items:
        title = item.get("title", "")
        url = item.get("html_url", "")
        if url in seen_bounties:
            continue
        seen_bounties.add(url)
        
        has_money = any(s in title for s in ["$", "USDC", "sats", "BTC", "ETH"])
        if not has_money:
            continue
        
        repo = item.get("repository_url", "").split("/")[-1]
        if item.get("comments", 99) == 0:
            found += 1
            log(f"🎯 BOUNTY FOUND: {repo}: {title[:60]}", "bounty")
            log(f"   {url}", "bounty")
            import webbrowser
            webbrowser.open(url)
    
    if found == 0:
        log(f"🔍 Searched {len(items)} issues — no new $ bounties", "info")
    else:
        log(f"🎯 Found {found} new funded bounties! Opened in browser.", "bounty")

# ============================================================
# PR MONITOR
# ============================================================
def check_prs():
    global bot_prs
    pr_states = []
    for repo, num, name in PRS:
        d = gh(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if not isinstance(d, dict) or d.get("error"):
            pr_states.append({"name": name, "state": "error", "comments": 0})
            continue
        
        merged = d.get("merged", False)
        state = d.get("state", "?")
        comments = d.get("comments", 0)
        
        if merged:
            log(f"💰💰💰 MERGED! {name} — {repo}#{num}", "money")
            import webbrowser
            webbrowser.open(f"https://github.com/{repo}/pull/{num}")
            check_wallet()
            pr_states.append({"name": name, "state": "merged", "comments": comments})
        elif state == "open":
            log(f"📋 {name}: open ({comments}c)", "info")
            pr_states.append({"name": name, "state": "open", "comments": comments})
        else:
            log(f"❌ {name}: {state}", "alert")
            pr_states.append({"name": name, "state": "closed", "comments": comments})
    
    bot_prs = pr_states

# ============================================================
# WALLET MONITOR
# ============================================================
def check_wallet():
    global last_balance, bot_stats
    try:
        data = json.dumps({"jsonrpc":"2.0","method":"eth_getBalance","params":[WALLET,"latest"],"id":1}).encode()
        req = urllib.request.Request("https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n", data=data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
        bal = int(result.get("result","0x0"), 16) / 1e18
        usd = bal * 2700
        
        if last_balance > 0 and bal > last_balance * 1.01:
            diff = bal - last_balance
            log(f"💰💰💰 PAYMENT! +{diff:.6f} ETH (+${diff*2700:.2f})", "money")
            import webbrowser
            webbrowser.open(f"https://basescan.org/address/{WALLET}")
        
        # USDC
        addr = WALLET.lower().replace("0x","").zfill(64)
        usdc_data = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913","data":f"0x70a08231{addr}"}, "latest"],"id":1}).encode()
        usdc_req = urllib.request.Request("https://base-mainnet.g.alchemy.com/v2/alch_BUo0TYqkD24rLEzrz4U3n", data=usdc_data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(usdc_req, timeout=10) as r:
            usdc_result = json.loads(r.read().decode())
        usdc_bal = int(usdc_result.get("result","0x0"), 16) / 1e6
        
        log(f"💵 ETH: ${usd:.2f} | USDC: {usdc_bal:.6f}", "money")
        bot_stats["eth"] = f"${usd:.2f}"
        last_balance = bal
    except Exception as e:
        log(f"💵 Wallet error: {str(e)[:40]}", "alert")

# ============================================================
# FRANTIC MONITOR
# ============================================================
def check_frantic():
    global last_frantic, bot_stats
    try:
        req = urllib.request.Request(f"https://gofrantic.com/v1/agents/{FRANTIC}/status")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        earned = d.get("agent",{}).get("earnedUsd",0)
        opens = d.get("work",{}).get("open",[])
        stage = opens[0].get("stage","?") if opens else "none"
        
        if earned > last_frantic and last_frantic >= 0:
            log(f"💰💰💰 FRANTIC PAID! ${earned}!", "money")
            import webbrowser
            webbrowser.open(f"https://gofrantic.com/a/{FRANTIC}")
        
        log(f"🤖 Frantic: ${earned} | {stage}", "info")
        bot_stats["frantic"] = f"${earned}"
        last_frantic = earned
    except Exception as e:
        log(f"🤖 Frantic error: {str(e)[:40]}", "alert")

# ============================================================
# XLM + BTC
# ============================================================
def check_xlm_btc():
    try:
        req = urllib.request.Request(f"https://horizon.stellar.org/accounts/{XLM}")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        bal = d.get("balances",[{}])[0].get("balance","0")
        log(f"💎 XLM: {bal}", "info")
    except: pass
    try:
        req = urllib.request.Request(f"https://blockchain.info/rawaddr/{BTC}?limit=1")
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        bal = d.get("final_balance",0) / 1e8
        if bal > 0:
            log(f"₿ BTC: {bal:.8f}", "money")
    except: pass

# ============================================================
# MAIN
# ============================================================
def run_cycle():
    log("=" * 50)
    log("🚜 BULLDOZER CYCLE START", "info")
    
    log("--- 📧 Email ---", "info")
    check_email()
    
    log("--- 🔍 Bounty Hunter ---", "info")
    hunt_bounties()
    
    log("--- 📋 PRs ---", "info")
    check_prs()
    
    log("--- 💵 Wallet ---", "info")
    check_wallet()
    
    log("--- 🤖 Frantic ---", "info")
    check_frantic()
    
    log("--- 💎 XLM/BTC ---", "info")
    check_xlm_btc()
    
    log("⏳ Next cycle: 5 min", "info")

def main():
    log("🚜🚜🚜 BULLDOZER v4 STARTED 🚜🚜🚜")
    log(f"📊 Monitoring: {len(PRS)} PRs + Frantic + ETH + XLM + BTC + Email")
    log(f"🔍 Bounty hunter: active")
    log(f"📧 Email monitor: active")
    log(f"🖥️  Dashboard: http://localhost:9876")
    log("")
    
    # Start dashboard in background thread
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    time.sleep(2)
    
    # Open dashboard in browser
    import webbrowser
    webbrowser.open("http://localhost:9876")
    log("🖥️  Dashboard opened in browser!")
    
    # Main loop
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Bot stopped by user.")
            break
        except Exception as e:
            log(f"⚠️ Cycle error: {str(e)[:80]}", "alert")
        time.sleep(300)

if __name__ == "__main__":
    main()
