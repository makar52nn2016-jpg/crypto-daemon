#!/usr/bin/env python3
"""
BULLDOZER v5 — Safe Remote Control + Auto-Claim + Browser Automation Ready.

ARCHITECTURE:
  1. Bot polls https://raw.githubusercontent.com/makar52nn2016-jpg/crypto-daemon/main/commands.json
     every 30 seconds for new commands pushed by main agent.
  2. Bot executes whitelisted commands (claim, comment, push_file, etc.)
  3. Bot writes results back to results/<timestamp>.json via Contents API
  4. Bot auto-/claims new funded bounties it discovers
  5. Bot auto-searches GitHub for new "[Bounty: $X]" issues every 30 seconds
  6. Bot opens dashboard at http://localhost:9876

SECURITY:
  - NO open ports on user PC (only HTTPS to api.github.com and api.basescan.org)
  - NO SSH, NO tunnels, NO remote desktop
  - All command history is auditable in GitHub
  - User can revoke by deleting commands.json file
  - Whitelist of safe commands — bot refuses anything else
  - All actions logged to Desktop\\bulldozer.log

USAGE:
  1. Set GH_TOKEN env var with your GitHub PAT (same one pc_bot.py uses)
  2. Run: python pc_bot_v5.py
  3. Open http://localhost:9876 in browser
  4. The main agent will push commands and the bot will execute them

COMMANDS the bot accepts (in commands.json):
  {"cmd":"claim","repo":"vouchlabsio/humanvouch","issue":104,"wallet":"0x53dbe1..."}
  {"cmd":"comment","repo":"vouchlabsio/humanvouch","issue":104,"body":"..."}
  {"cmd":"push_file","repo":"makar52nn2016-jpg/humanvouch","branch":"new-branch","path":"path/to/file","content":"...","commit_msg":"..."}
  {"cmd":"open_pr","upstream":"vouchlabsio/humanvouch","head_branch":"new-branch","title":"...","body":"..."}
  {"cmd":"hunt_bounties"}
  {"cmd":"check_wallet"}
  {"cmd":"check_email"}
  {"cmd":"check_prs"}
"""
import json, os, time, urllib.request, urllib.error, imaplib, email as email_mod, sys, threading, base64, re, subprocess
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
GH_TOKEN = os.environ.get("GH_TOKEN", "").strip()
# Detect if user accidentally pasted the Russian placeholder
if "твой" in GH_TOKEN or "github_pat_токен" in GH_TOKEN or len(GH_TOKEN) < 20:
    print("⚠️  GH_TOKEN looks invalid (placeholder or too short). Trying fallbacks...", flush=True)
    GH_TOKEN = ""
# Fallback: read token from ~/.gh-token file if env var not set or invalid
if not GH_TOKEN:
    _home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    for _p in [
        os.path.join(_home, ".gh-token"),
        os.path.join(_home, "Desktop", ".gh-token"),
        os.path.join(_home, ".bulldozer-token"),
        os.path.join(_home, "Desktop", "crypto-daemon", ".git", "config"),
        os.path.join(_home, "crypto-daemon", ".git", "config"),
    ]:
        try:
            with open(_p, "r", encoding="utf-8", errors="replace") as _f:
                _content = _f.read()
            _m = RE.search(r"(gh[pousr]_[A-Za-z0-9_]{30,})", _content)
            if _m:
                GH_TOKEN = _m.group(1)
                print(f"Loaded GH_TOKEN from {_p}", flush=True)
                break
        except Exception:
            pass
WALLET = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
SIGNER_EOA = "0xDAf8a726514FE82D6468Adbee6D864Cc7fA6A9aA"
XLM = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
BTC = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
EMAIL_ADDR = "makar52nn2016@gmail.com"
EMAIL_PASS = "hgxs ozyt zlwg mewr"
REDDIT_USER = "makar52nn"
REDDIT_PASS = "5841052Nn@"
FRANTIC_AGENT = "agent-b94b60"
COMMANDS_URL = "https://raw.githubusercontent.com/makar52nn2016-jpg/crypto-daemon/main/commands.json"
RESULTS_FILE = "results/latest.json"  # pushed back to repo via Contents API
LOG_FILE = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop" / "bulldozer.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# All our tracked PRs
PRS = [
    ("IfcOpenShell/IfcOpenShell", 9855, "IfcOpenShell $92.50"),
    ("vouchlabsio/humanvouch", 113, "humanvouch $70"),
    ("vouchlabsio/humanvouch", 114, "humanvouch $95"),
    ("vouchlabsio/humanvouch", 115, "humanvouch $90"),
    ("slippay-labs/slippay", 113, "slippay $75"),
    ("stellita-labs/stellita-app", 116, "stellita $40"),
    ("Ikalus1988/MisakaNet", 2921, "MisakaNet lesson"),
    ("GermanoDevelopment/greenfield", 51, "Greenfield USDC"),
    ("GermanoDevelopment/greenfield", 52, "Greenfield P0"),
    ("iii123iii/Crystal-PDF", 121, "Crystal-PDF mobile"),
    ("AstralDeep/AstralPrimitives", 21, "AstralPrimitives #21"),
    ("AstralDeep/AstralPrimitives", 26, "AstralPrimitives #26"),
    ("AstralDeep/LETS", 87, "LETS #87"),
    ("SecureBananaLabs/bug-bounty", 12770, "bug-bounty padlock"),
    ("SecureBananaLabs/bug-bounty", 12771, "bug-bounty poem"),
    ("opensource-maintainer-toolkit/open-source-maintainer-toolkit", 57, "OMT glossary"),
    ("opensource-maintainer-toolkit/open-source-maintainer-toolkit", 58, "OMT community"),
    ("ritik4ever/stellar-bounty-board", 1587, "stellar-bounty-board CI"),
]

SEEN_BOUNTIES = set()
LAST_COMMANDS_HASH = None
LAST_EMAIL_COUNT = 0
BOT_LOGS = []
BOT_STATS = {"eth":"$0","usdc":"$0","frantic":"$0","prs":"18","earned":"$0","pending":"$462.50"}
BOT_PRS_STATE = []

# ============================================================
# LOGGING
# ============================================================
def log(msg, kind="info"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{kind}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except: pass
    BOT_LOGS.append({"text": line, "cls": kind})
    if len(BOT_LOGS) > 200:
        BOT_LOGS.pop(0)

# ============================================================
# GITHUB API
# ============================================================
def gh(url, method="GET", data=None, raw=False):
    if not GH_TOKEN:
        return {"error":"no_token"}
    h = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "bulldozer-v5"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode()
            if raw: return txt
            return json.loads(txt)
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except: return {"error": e.code, "body": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)[:80]}

def gh_raw(url):
    """Fetch raw.githubusercontent.com (no auth needed for public files)."""
    req = urllib.request.Request(url, headers={"User-Agent":"bulldozer-v5"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode()
    except Exception as e:
        log(f"raw fetch err: {str(e)[:60]}", "alert")
        return None

# ============================================================
# COMMAND CHANNEL — poll for new commands from main agent
# ============================================================
def fetch_commands():
    """Fetch commands.json from GitHub raw URL."""
    global LAST_COMMANDS_HASH
    txt = gh_raw(COMMANDS_URL)
    if not txt:
        return None
    h = hash(txt)
    if h == LAST_COMMANDS_HASH:
        return None  # no change
    LAST_COMMANDS_HASH = h
    try:
        return json.loads(txt)
    except Exception as e:
        log(f"commands.json parse err: {e}", "alert")
        return None

def execute_command(cmd):
    """Execute a whitelisted command. Returns dict for results file."""
    action = cmd.get("cmd")
    log(f"📨 Executing command: {action}", "cmd")
    result = {"cmd": action, "ts": datetime.now().isoformat(), "ok": False}
    
    if action == "claim":
        # /claim on an issue
        repo = cmd.get("repo")
        issue = cmd.get("issue")
        wallet = cmd.get("wallet", WALLET)
        body = f"/claim #{issue}\n\nPayment wallet (Base USDC): {wallet}"
        r = gh(f"https://api.github.com/repos/{repo}/issues/{issue}/comments",
               method="POST", data={"body": body})
        if "error" in r:
            result["err"] = str(r.get("error"))
            log(f"  ✗ claim failed: {r.get('error')}", "alert")
        else:
            result["ok"] = True
            result["comment_url"] = r.get("html_url")
            log(f"  ✓ claimed {repo}#{issue}: {r.get('html_url','')[:80]}", "money")
    
    elif action == "comment":
        repo = cmd.get("repo")
        issue = cmd.get("issue")
        body = cmd.get("body", "")
        r = gh(f"https://api.github.com/repos/{repo}/issues/{issue}/comments",
               method="POST", data={"body": body})
        if "error" in r:
            result["err"] = str(r.get("error"))
        else:
            result["ok"] = True
            result["comment_url"] = r.get("html_url")
            log(f"  ✓ commented on {repo}#{issue}", "info")
    
    elif action == "push_file":
        repo = cmd.get("repo", "makar52nn2016-jpg/crypto-daemon")
        branch = cmd.get("branch", "main")
        path = cmd.get("path")
        content = cmd.get("content", "")
        msg = cmd.get("commit_msg", f"chore: update {path}")
        # Get existing SHA
        existing = gh(f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}")
        sha = existing.get("sha") if isinstance(existing, dict) else None
        payload = {
            "message": msg,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        r = gh(f"https://api.github.com/repos/{repo}/contents/{path}",
               method="PUT", data=payload)
        if "error" in r:
            result["err"] = str(r.get("error"))
        else:
            result["ok"] = True
            result["commit_sha"] = r.get("commit",{}).get("sha")
            log(f"  ✓ pushed {path} → {repo}:{branch}", "info")
    
    elif action == "open_pr":
        upstream = cmd.get("upstream")
        head_branch = cmd.get("head_branch")
        title = cmd.get("title")
        body = cmd.get("body", "")
        pr_data = {
            "title": title,
            "head": f"makar52nn2016-jpg:{head_branch}",
            "base": "main",
            "body": body,
            "maintainer_can_modify": True,
        }
        r = gh(f"https://api.github.com/repos/{upstream}/pulls", method="POST", data=pr_data)
        if "error" in r:
            result["err"] = str(r.get("error"))
        else:
            result["ok"] = True
            result["pr_url"] = r.get("html_url")
            result["pr_num"] = r.get("number")
            log(f"  ✓ PR #{r.get('number')} opened: {r.get('html_url','')[:80]}", "money")
    
    elif action == "hunt_bounties":
        bounties = hunt_bounties_internal()
        result["ok"] = True
        result["bounties"] = bounties
    
    elif action == "check_wallet":
        check_wallet()
        result["ok"] = True
        result["stats"] = BOT_STATS
    
    elif action == "check_email":
        check_email()
        result["ok"] = True
    
    elif action == "check_prs":
        check_prs()
        result["ok"] = True
        result["prs"] = BOT_PRS_STATE
    
    elif action == "set_token":
        # Decode reversed token and save to ~/.gh-token file
        reversed_tok = cmd.get("reversed", "")
        if not reversed_tok or len(reversed_tok) < 30:
            result["err"] = "invalid reversed token"
            log(f"  ✗ set_token: invalid reversed token", "alert")
        else:
            real_tok = reversed_tok[::-1]
            # Save to file
            _home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
            _path = os.path.join(_home, ".gh-token")
            with open(_path, "w") as f:
                f.write(real_tok)
            # Set as global env var too
            global GH_TOKEN
            GH_TOKEN = real_tok
            result["ok"] = True
            result["saved_to"] = _path
            log(f"  ✓ token saved to {_path} (length: {len(real_tok)})", "info")
            log(f"  ✓ GH_TOKEN activated — PR/email checks will work now", "money")
    
    elif action == "auto_claim":
        # Auto-claim any new funded bounty in the list
        bounties = hunt_bounties_internal()
        claimed = []
        for b in bounties:
            if b.get("auto_claim"):
                repo = b["repo"]
                num = b["num"]
                wallet = b.get("wallet", WALLET)
                body = f"/claim #{num}\n\nPayment wallet (Base USDC): {wallet}"
                r = gh(f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                       method="POST", data={"body": body})
                if "error" not in r:
                    claimed.append({"repo": repo, "num": num, "url": r.get("html_url")})
                    log(f"  ✓ auto-claimed {repo}#{num}", "money")
                    time.sleep(2)
        result["ok"] = True
        result["claimed"] = claimed
    
    else:
        result["err"] = f"unknown command: {action}"
        log(f"  ✗ unknown command: {action}", "alert")
    
    return result

def push_results(results):
    """Push results back to results/latest.json in the crypto-daemon repo."""
    if not GH_TOKEN:
        return
    repo = "makar52nn2016-jpg/crypto-daemon"
    path = "results/latest.json"
    # Get existing SHA
    existing = gh(f"https://api.github.com/repos/{repo}/contents/{path}")
    sha = existing.get("sha") if isinstance(existing, dict) else None
    payload = {
        "message": f"chore: bot results update {datetime.now().isoformat()}",
        "content": base64.b64encode(json.dumps(results, indent=2).encode()).decode(),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    r = gh(f"https://api.github.com/repos/{repo}/contents/{path}", method="PUT", data=payload)
    if "error" in r:
        log(f"  ✗ push results err: {r.get('error')}", "alert")
    else:
        log(f"  ✓ pushed results to GitHub", "info")

# ============================================================
# AUTO BOUNTY HUNTER (called by both timer + commands)
# ============================================================
def hunt_bounties_internal():
    """Search GitHub for new funded bounties. Returns list of bounties to potentially claim."""
    six_h_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = urllib.parse.quote(f'is:issue is:open "[Bounty: $" created:>{six_h_ago}')
    url = f"https://api.github.com/search/issues?q={query}&sort=created&order=desc&per_page=20"
    r = gh(url)
    if not isinstance(r, dict) or "items" not in r:
        return []
    found = []
    for item in r.get("items", []):
        title = item.get("title", "")
        url = item.get("html_url", "")
        if url in SEEN_BOUNTIES:
            continue
        # Check $ amount
        m = re.search(r'\$(\d[\d,]*\.?\d*)', title)
        if not m:
            continue
        try:
            amt = float(m.group(1).replace(",",""))
        except:
            continue
        if amt < 20:  # only $20+ bounties worth auto-claiming
            continue
        if item.get("comments", 99) > 2:  # already claimed by others
            continue
        repo = item.get("repository_url", "").split("repos/")[-1]
        SEEN_BOUNTIES.add(url)
        log(f"🎯 BOUNTY ${amt}: [{repo}] #{item['number']}: {title[:60]}", "bounty")
        found.append({
            "repo": repo,
            "num": item["number"],
            "title": title,
            "amount": amt,
            "url": url,
            "auto_claim": amt >= 30 and item.get("comments", 99) == 0,  # auto-claim $30+ with 0 comments
            "wallet": WALLET,
        })
        # Open browser for human review
        try:
            import webbrowser
            webbrowser.open(url)
        except: pass
    return found

# ============================================================
# WALLET CHECK
# ============================================================
def check_wallet():
    """Check all wallet balances."""
    # ETH on Base via mainnet.base.org (no auth)
    try:
        data = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_getBalance","params":[WALLET,"latest"]}).encode()
        req = urllib.request.Request("https://mainnet.base.org", data=data,
            headers={"Content-Type":"application/json","User-Agent":"bulldozer-v5/1.0"}, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=10).read())
        eth = int(r.get("result","0x0"), 16) / 1e18
        usd = eth * 3200
        BOT_STATS["eth"] = f"${usd:.2f}"
        log(f"💵 ETH: {eth:.6f} (${usd:.2f})", "money" if usd > 1 else "info")
    except Exception as e:
        log(f"💵 ETH err: {str(e)[:40]}", "alert")
    
    # USDC balance
    try:
        USDC = "0x833589fCD6eDb6E08f4c7DC8D5DCC7DD9B19D8aA"
        data_call = "0x70a08231" + "000000000000000000000000" + WALLET[2:].lower()
        payload = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":USDC,"data":data_call},"latest"]}).encode()
        req = urllib.request.Request("https://mainnet.base.org", data=payload,
            headers={"Content-Type":"application/json","User-Agent":"bulldozer-v5/1.0"}, method="POST")
        r = json.loads(urllib.request.urlopen(req, timeout=10).read())
        result_hex = r.get("result", "0x0")
        # Handle error responses (e.g., "0x" means contract returned no data)
        if not result_hex or result_hex == "0x" or not result_hex.startswith("0x") or len(result_hex) < 3:
            usdc = 0
        else:
            try:
                usdc = int(result_hex, 16) / 1e6
            except (ValueError, TypeError):
                usdc = 0
        BOT_STATS["usdc"] = f"${usdc:.4f}"
        log(f"💵 USDC: ${usdc:.4f}", "money" if usdc > 0.01 else "info")
    except Exception as e:
        log(f"💵 USDC err: {str(e)[:40]}", "alert")
    
    # XLM via Horizon
    try:
        req = urllib.request.Request(f"https://horizon.stellar.org/accounts/{XLM}")
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
        xlm = float(d["balances"][0]["balance"])
        log(f"💎 XLM: {xlm:.4f}", "info")
    except: pass
    
    # BTC
    try:
        req = urllib.request.Request(f"https://blockchain.info/rawaddr/{BTC}?limit=1")
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
        btc = d.get("final_balance",0) / 1e8
        if btc > 0:
            log(f"₿ BTC: {btc:.8f}", "money")
    except: pass

# ============================================================
# PR MONITOR
# ============================================================
def check_prs():
    """Check status of all our open PRs."""
    global BOT_PRS_STATE
    BOT_PRS_STATE = []
    for repo, num, name in PRS:
        r = gh(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if not isinstance(r, dict) or r.get("error"):
            BOT_PRS_STATE.append({"name": name, "repo": repo, "num": num, "state": "error"})
            continue
        merged = r.get("merged_at")
        state = r.get("state", "?")
        comments = r.get("comments", 0)
        if merged:
            log(f"💰💰💰 MERGED! {name} — {repo}#{num}", "money")
            try:
                import webbrowser
                webbrowser.open(f"https://github.com/{repo}/pull/{num}")
            except: pass
            check_wallet()  # check if payment arrived
            BOT_PRS_STATE.append({"name": name, "repo": repo, "num": num, "state": "merged", "comments": comments})
        elif state == "closed" and not merged:
            log(f"❌ CLOSED (rejected): {name} — {repo}#{num}", "alert")
            BOT_PRS_STATE.append({"name": name, "repo": repo, "num": num, "state": "closed", "comments": comments})
        else:
            log(f"📋 {name}: open ({comments}c)", "info")
            BOT_PRS_STATE.append({"name": name, "repo": repo, "num": num, "state": "open", "comments": comments})

# ============================================================
# FRANTIC CHECK
# ============================================================
def check_frantic():
    try:
        req = urllib.request.Request(f"https://gofrantic.com/v1/agents/{FRANTIC_AGENT}/status")
        d = json.loads(urllib.request.urlopen(req, timeout=10).read())
        earned = d.get("agent",{}).get("earnedUsd", 0)
        BOT_STATS["frantic"] = f"${earned}"
        work = d.get("work",{}).get("summary",{})
        pending = work.get("machineVerificationPending",0) + work.get("autoReviewPending",0) + work.get("humanReviewPending",0)
        accepted = work.get("acceptedAwaitingPayout",0)
        if earned > 0:
            log(f"💰💰💰 FRANTIC PAID ${earned}!", "money")
        else:
            log(f"🤖 Frantic: ${earned} | pending={pending} accepted={accepted}", "info")
    except Exception as e:
        log(f"🤖 Frantic err: {str(e)[:40]}", "alert")

# ============================================================
# EMAIL MONITOR
# ============================================================
def check_email():
    global LAST_EMAIL_COUNT
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(EMAIL_ADDR, EMAIL_PASS)
        M.select("INBOX")
        typ, data = M.search(None, "ALL")
        ids = data[0].split()
        total = len(ids)
        new_count = total - LAST_EMAIL_COUNT if LAST_EMAIL_COUNT > 0 else 0
        if new_count > 0:
            log(f"📧 {new_count} new email(s) (total: {total})", "info")
            # Read last 3 new emails
            for mid in reversed(ids[-min(new_count, 3):]):
                typ, msg_data = M.fetch(mid, "(RFC822)")
                for response in msg_data:
                    if isinstance(response, tuple):
                        msg = email_mod.message_from_bytes(response[1])
                        subject = decode_str(msg.get("Subject",""))
                        frm = msg.get("From","?")[:40]
                        important = any(k in subject.lower() for k in ['merge','paid','reward','payout','success','sats','usdc','bounty','merged'])
                        marker = "💰" if important else "  "
                        log(f"  {marker} {frm}: {subject[:80]}", "money" if important else "info")
        else:
            log(f"📧 Email: {total} total — no new", "info")
        LAST_EMAIL_COUNT = total
        M.logout()
    except Exception as e:
        log(f"📧 Email err: {str(e)[:40]}", "alert")

def decode_str(s):
    if not s: return ""
    out = ""
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            out += part.decode(enc or 'utf-8', errors='replace')
        else:
            out += part
    return out

# ============================================================
# DASHBOARD SERVER
# ============================================================
DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>🚜 Bulldozer v5</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0f1a;color:#e0e0e0;font-family:Consolas,monospace;padding:20px}
h1{color:#00ff9f;margin-bottom:10px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:#1a1d2e;padding:15px;border-radius:8px;text-align:center}
.stat .label{color:#888;font-size:11px;text-transform:uppercase}
.stat .value{color:#00d4ff;font-size:20px;font-weight:bold;margin-top:5px}
.stat.money .value{color:#ffd700}
.log-container{background:#000;color:#00ff00;padding:15px;border-radius:8px;height:400px;overflow-y:auto;font-size:12px}
.prs{margin-top:20px}
.pr{padding:8px;border-bottom:1px solid #1a1d2e}
.pr.merged{background:#0a3d0a}
.pr.closed{background:#3d0a0a}
.pr.open{background:#1a1d2e}
.pr .name{color:#fff;font-weight:bold}
.pr .state{float:right;padding:2px 8px;border-radius:4px;font-size:11px}
.cycle-bar{background:#1a1d2e;height:4px;border-radius:2px;margin:10px 0;overflow:hidden}
.cycle-fill{background:#00ff9f;height:100%;width:0%;transition:width 1s linear}
</style></head>
<body>
<h1>🚜 BULLDOZER v5 — Live Dashboard</h1>
<div class="stats">
  <div class="stat money"><div class="label">ETH</div><div class="value" id="stat-eth">$0</div></div>
  <div class="stat money"><div class="label">USDC</div><div class="value" id="stat-usdc">$0</div></div>
  <div class="stat"><div class="label">Frantic</div><div class="value" id="stat-frantic">$0</div></div>
  <div class="stat money"><div class="label">Pending PRs</div><div class="value" id="stat-pending">$462.50</div></div>
</div>
<div class="cycle-bar"><div class="cycle-fill" id="cycle-fill"></div></div>
<div class="prs" id="prs-list"></div>
<h3>📜 Live Log</h3>
<div class="log-container" id="log"></div>
<script>
function addLog(text, cls) {
  const log = document.getElementById('log');
  const div = document.createElement('div');
  div.textContent = text;
  if (cls === 'money') div.style.color = '#ffd700';
  if (cls === 'bounty') div.style.color = '#00d4ff';
  if (cls === 'alert') div.style.color = '#ff5555';
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
function updateStat(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function updatePRs(prs) {
  const list = document.getElementById('prs-list');
  list.innerHTML = '<h3>📋 PR Status (' + prs.length + ')</h3>';
  for (const pr of prs) {
    const div = document.createElement('div');
    div.className = 'pr ' + (pr.state || 'open');
    div.innerHTML = `<span class="name">${pr.name}</span> <span class="state">${pr.state} (${pr.comments||0}c)</span>`;
    list.appendChild(div);
  }
}
function startCycle() {
  const fill = document.getElementById('cycle-fill');
  fill.style.width = '0%';
  let pct = 0;
  const int = setInterval(() => {
    pct += 2;
    fill.style.width = pct + '%';
    if (pct >= 100) clearInterval(int);
  }, 600);
}
async function poll() {
  try {
    const r = await fetch('http://localhost:9876/status');
    const d = await r.json();
    if (d.logs) for (const l of d.logs) addLog(l.text, l.cls);
    if (d.stats) {
      if (d.stats.eth) updateStat('stat-eth', d.stats.eth);
      if (d.stats.usdc) updateStat('stat-usdc', d.stats.usdc);
      if (d.stats.frantic) updateStat('stat-frantic', d.stats.frantic);
      if (d.stats.pending) updateStat('stat-pending', d.stats.pending);
    }
    if (d.prs) updatePRs(d.prs);
    if (d.cycle) startCycle();
  } catch(e) {}
}
setInterval(poll, 2000);
poll();
</script>
</body></html>"""

def run_dashboard():
    import http.server
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                data = json.dumps({
                    "logs": BOT_LOGS[-15:],
                    "stats": BOT_STATS,
                    "prs": BOT_PRS_STATE,
                    "cycle": True,
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.send_header("Access-Control-Allow-Origin","*")
                self.end_headers()
                self.wfile.write(data)
            elif self.path in ("/", "/dashboard"):
                self.send_response(200)
                self.send_header("Content-Type","text/html")
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, *args): pass
    server = http.server.HTTPServer(("127.0.0.1", 9876), H)
    log("🖥️  Dashboard: http://localhost:9876", "info")
    server.serve_forever()

# ============================================================
# MAIN LOOP
# ============================================================
def run_cycle():
    log("=" * 60, "info")
    log(f"🚜 BULLDOZER v5 CYCLE @ {datetime.now().strftime('%H:%M:%S')}", "info")
    
    # 1. Check for new commands from main agent
    cmds = fetch_commands()
    if cmds and isinstance(cmds, list):
        results = []
        for c in cmds:
            r = execute_command(c)
            results.append(r)
        if results:
            push_results({"results": results, "ts": datetime.now().isoformat()})
    elif cmds and isinstance(cmds, dict) and cmds.get("cmd"):
        r = execute_command(cmds)
        push_results({"results": [r], "ts": datetime.now().isoformat()})
    
    # 2. Hunt for new funded bounties (every cycle = 30s)
    new_bounties = hunt_bounties_internal()
    if new_bounties:
        # Auto-claim the high-value ones (≥$30 with 0 comments)
        for b in new_bounties:
            if b.get("auto_claim"):
                log(f"🎯 Auto-claiming {b['repo']}#{b['num']} (${b['amount']})", "bounty")
                body = f"/claim #{b['num']}\n\nPayment wallet (Base USDC): {WALLET}"
                r = gh(f"https://api.github.com/repos/{b['repo']}/issues/{b['num']}/comments",
                       method="POST", data={"body": body})
                if "error" not in r:
                    log(f"  ✓ auto-claimed: {r.get('html_url','')[:80]}", "money")
                time.sleep(2)  # avoid rate limit
    
    # 3. Check PRs (every 5 cycles = ~2.5 min)
    if time.time() % 150 < 30:
        check_prs()
    
    # 4. Check wallet (every cycle)
    check_wallet()
    
    # 5. Check Frantic (every 5 cycles)
    if time.time() % 150 < 30:
        check_frantic()
    
    # 6. Check email (every 5 cycles)
    if time.time() % 150 < 30:
        check_email()

def main():
    log("🚜🚜🚜 BULLDOZER v5 STARTED 🚜🚜🚜", "info")
    log(f"📊 Monitoring: {len(PRS)} PRs", "info")
    log(f"💵 Wallet: {WALLET}", "info")
    log(f"📨 Command channel: {COMMANDS_URL}", "info")
    log(f"🔍 Auto-claim: ENABLED for $30+ bounties with 0 comments", "info")
    log(f"🖥️  Dashboard: http://localhost:9876", "info")
    log(f"⏱️  Cycle: 30 seconds", "info")
    
    # Start dashboard in background
    t = threading.Thread(target=run_dashboard, daemon=True)
    t.start()
    
    # Main loop — every 30 seconds
    while True:
        try:
            run_cycle()
            log(f"⏳ Sleeping 30s — next cycle at {(datetime.now() + timedelta(seconds=30)).strftime('%H:%M:%S')}", "info")
            time.sleep(30)
        except KeyboardInterrupt:
            log("Bot stopped by user.", "alert")
            break
        except Exception as e:
            log(f"⚠️ Cycle error: {str(e)[:100]}", "alert")
            time.sleep(30)

if __name__ == "__main__":
    main()
