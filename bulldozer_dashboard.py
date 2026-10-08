#!/usr/bin/env python3
"""
BULLDOZER DASHBOARD v4 — Real-time GUI for the 24/7 bounty bot.
Shows what the bot is doing right now: PR statuses, wallet, bounties, email alerts, live log.
Auto-refreshes every 5 minutes. Opens a visible window on the user's Windows PC.

Usage on Windows:
    python bulldozer_dashboard.py

Or via PowerShell:
    py bulldozer_dashboard.py
"""
import json, os, sys, time, threading, urllib.request, urllib.error, re
import imaplib, email as email_lib
from email.header import decode_header
from datetime import datetime, timezone, timedelta
from pathlib import Path

# tkinter is pre-installed on Windows
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ============================================================
# CONFIG  — fetch token from .git/config or env
# ============================================================
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "").strip()
if not GITHUB_TOKEN:
    # Try to read from the local git config in the cloned daemon repo
    for cand in [
        r"C:\bulldozer\crypto-daemon\.git\config",
        os.path.expanduser("~/bulldozer/crypto-daemon/.git/config"),
        "crypto-daemon/.git/config",
    ]:
        try:
            with open(cand) as f:
                cfg = f.read()
            m = re.search(r'(gh[pousr]_[A-Za-z0-9_]{20,})', cfg)
            if m:
                GITHUB_TOKEN = m.group(1)
                break
        except Exception:
            pass

WALLET_BASE = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
SIGNER_EOA = "0xDAf8a726514FE82D6468Adbee6D864Cc7fA6A9aA"
BTC_WALLET = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
XLM_WALLET = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
GMAIL_USER = "makar52nn2016@gmail.com"
GMAIL_APP_PASS = "hgxs ozyt zlwg mewr"

# Our active PRs (repo, number, $bounty)
WATCH_PRS = [
    ("IfcOpenShell/IfcOpenShell",        9855, 92.50),
    ("vouchlabsio/humanvouch",           113,  70.00),
    ("GermanoDevelopment/greenfield",     51,  0),  # USDC, amount unknown
    ("GermanoDevelopment/greenfield",     52,  0),
    ("Ikalus1988/MisakaNet",            2921,  0),  # lesson credit only
    ("iii123iii/Crystal-PDF",            121,  0),  # uncertain
    ("AstralDeep/AstralPrimitives",       26,  0),
    ("AstralDeep/AstralPrimitives",       21,  0),
    ("AstralDeep/LETS",                   87,  0),
    ("SecureBananaLabs/bug-bounty",     12770,  0),
    ("SecureBananaLabs/bug-bounty",     12771,  0),
    ("opensource-maintainer-toolkit/open-source-maintainer-toolkit", 57, 0),
    ("opensource-maintainer-toolkit/open-source-maintainer-toolkit", 58, 0),
    ("ritik4ever/stellar-bounty-board", 1587,  0),
]

# Active funded bounty targets (where we have a delivery/PR pending payout)
FUNDED_TARGETS = [
    ("IfcOpenShell PR #9855",       92.50, "Awaiting steering committee review (open since Oct 8 05:59 UTC)"),
    ("humanvouch PR #113",          70.00, "Opened Oct 8 07:11 UTC, fixes #109 ($70 bounty)"),
    ("Frantic #129 ($16)",          16.00, "Delivery submitted, pending Frantic bot verification"),
    ("Frantic #128 ($8)",            8.00, "Delivery submitted, pending Frantic bot verification"),
    ("Crystal-PDF PR #121",          0,    "Mobile-responsive landing fix, pending review"),
    ("AstralPrimitives #26/#21",    0,    "100 pts each — future token, no $ value yet"),
    ("AstralDeep LETS #87",          0,    "Test PR, pending maintainer"),
    ("Greenfield PRs #51/#52",       0,    "USDC bounty amount unknown"),
    ("MisakaNet PR #2921",           0,    "Lesson PR, awaiting CI/merge ($0 bounty)"),
]

LOG_FILE = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop" / "bulldozer.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# API HELPERS
# ============================================================
def github_api(url, method="GET", data=None):
    if not GITHUB_TOKEN:
        return {"error": "no_token"}
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "bulldozer-dashboard",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)[:100]}

def rpc_balance(addr):
    """Get ETH balance via Base RPC (no auth needed)."""
    data = json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_getBalance","params":[addr,"latest"]}).encode()
    req = urllib.request.Request(
        "https://mainnet.base.org",
        data=data,
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode())
        bal_wei = int(res.get("result","0x0"), 16)
        return bal_wei / 1e18
    except Exception:
        return None

def erc20_balance(token, who):
    data = "0x70a08231" + "000000000000000000000000" + who[2:].lower()
    payload = json.dumps({
        "jsonrpc":"2.0","id":1,"method":"eth_call",
        "params":[{"to":token,"data":data},"latest"]
    }).encode()
    req = urllib.request.Request("https://mainnet.base.org", data=payload,
        headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode())
        h = res.get("result","0x0")
        return int(h,16) if h and h.startswith("0x") else 0
    except Exception:
        return 0

def fmt_age(iso_ts):
    """Format a UTC ISO timestamp as 'Xh Ym ago'."""
    if not iso_ts:
        return "?"
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z","+00:00"))
        delta = datetime.now(timezone.utc) - ts
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        if h > 24:
            return f"{h//24}d {h%24}h"
        return f"{h}h {m}m"
    except Exception:
        return iso_ts[:16]

def decode_str(s):
    if not s: return ""
    out = ""
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            out += part.decode(enc or 'utf-8', errors='replace')
        else:
            out += part
    return out

def get_email_body(msg, max_chars=300):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    p = part.get_payload(decode=True)
                    body = p.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    break
                except Exception: pass
            elif ct == "text/html" and not body:
                try:
                    p = part.get_payload(decode=True)
                    body = p.decode(part.get_content_charset() or 'utf-8', errors='replace')
                except Exception: pass
    else:
        try:
            p = msg.get_payload(decode=True)
            body = p.decode(msg.get_content_charset() or 'utf-8', errors='replace')
        except Exception: pass
    return body[:max_chars]

def read_inbox(limit=8):
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(GMAIL_USER, GMAIL_APP_PASS)
        M.select("INBOX")
        typ, data = M.search(None, "ALL")
        ids = data[0].split()
        out = []
        for i in ids[-limit:]:
            typ, msg_data = M.fetch(i, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])
            out.append({
                "from": decode_str(msg.get("From","")),
                "subject": decode_str(msg.get("Subject","")),
                "date": msg.get("Date",""),
                "body": get_email_body(msg),
            })
        M.logout()
        return out
    except Exception as e:
        return [{"from":"error","subject":str(e)[:80],"date":"","body":""}]

# ============================================================
# GUI APP
# ============================================================
class BulldozerDashboard:
    def __init__(self, root):
        self.root = root
        root.title("🚜 BULLDOZER DASHBOARD — 24/7 Bounty Bot")
        root.geometry("1400x900")
        root.configure(bg="#0d0f1a")

        # Style
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#0d0f1a")
        style.configure("TLabel", background="#0d0f1a", foreground="#e0e0e0", font=("Consolas",10))
        style.configure("Title.TLabel", background="#0d0f1a", foreground="#00ff9f", font=("Consolas",16,"bold"))
        style.configure("Section.TLabel", background="#0d0f1a", foreground="#00d4ff", font=("Consolas",12,"bold"))
        style.configure("Money.TLabel", background="#0d0f1a", foreground="#ffd700", font=("Consolas",14,"bold"))
        style.configure("Header.TLabel", background="#1a1d2e", foreground="#00d4ff", font=("Consolas",11,"bold"))

        # Top banner
        top = ttk.Frame(root)
        top.pack(side="top", fill="x", padx=10, pady=5)
        ttk.Label(top, text="🚜 BULLDOZER DASHBOARD", style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="⏳ Initializing…")
        ttk.Label(top, textvariable=self.status_var, style="TLabel").pack(side="right")

        # Notebook (tabs)
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_prs = ttk.Frame(self.nb)
        self.tab_money = ttk.Frame(self.nb)
        self.tab_email = ttk.Frame(self.nb)
        self.tab_bounties = ttk.Frame(self.nb)
        self.tab_log = ttk.Frame(self.nb)

        self.nb.add(self.tab_prs, text="📋 PR Status")
        self.nb.add(self.tab_money, text="💰 Wallet & Money")
        self.nb.add(self.tab_bounties, text="🎯 Funded Bounties")
        self.nb.add(self.tab_email, text="📧 Email")
        self.nb.add(self.tab_log, text="📜 Live Log")

        self._build_prs_tab()
        self._build_money_tab()
        self._build_bounties_tab()
        self._build_email_tab()
        self._build_log_tab()

        # Footer with action buttons
        bot = ttk.Frame(root)
        bot.pack(side="bottom", fill="x", padx=10, pady=5)
        ttk.Button(bot, text="🔄 Refresh Now", command=self.refresh_async).pack(side="left", padx=5)
        ttk.Button(bot, text="🌐 Open Smart Account", command=lambda: self._open_url(f"https://basescan.org/address/{WALLET_BASE}")).pack(side="left", padx=5)
        ttk.Button(bot, text="🐙 Open GitHub PRs", command=self._open_prs_url).pack(side="left", padx=5)
        ttk.Button(bot, text="📬 Open Gmail", command=lambda: self._open_url("https://mail.google.com")).pack(side="left", padx=5)
        self.cycle_var = tk.StringVar(value="Next refresh: 5:00")
        ttk.Label(bot, textvariable=self.cycle_var, style="TLabel").pack(side="right")

        # Start the bot log capture
        self.log_lines = []
        self._load_existing_log()

        # Kick off async refresh
        self.refresh_async()
        # Start background refresher
        self._schedule_refresh(300)

    # --------- Build tabs ---------
    def _build_prs_tab(self):
        cols = ("repo","num","title","state","bounty","age","comments","updated")
        self.tree = ttk.Treeview(self.tab_prs, columns=cols, show="headings", height=15)
        for c, w in zip(cols, [180, 50, 280, 80, 70, 70, 80, 100]):
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        # Color tags
        self.tree.tag_configure("open_pending", background="#1a1d2e", foreground="#ffcc00")
        self.tree.tag_configure("merged", background="#0a3d0a", foreground="#00ff7f")
        self.tree.tag_configure("closed", background="#3d0a0a", foreground="#ff5555")
        self.tree.tag_configure("new_comment", background="#1a2e3d", foreground="#00d4ff")

    def _build_money_tab(self):
        frame = ttk.Frame(self.tab_money)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.wallet_var = tk.StringVar(value="⏳ Loading wallet…")
        ttk.Label(frame, textvariable=self.wallet_var, style="Money.TLabel").pack(anchor="w", pady=10)
        self.frantic_var = tk.StringVar(value="⏳ Loading Frantic…")
        ttk.Label(frame, textvariable=self.frantic_var, style="Money.TLabel").pack(anchor="w", pady=10)
        self.pending_var = tk.StringVar(value="⏳ Calculating pending…")
        ttk.Label(frame, textvariable=self.pending_var, style="Money.TLabel").pack(anchor="w", pady=10)
        ttk.Separator(frame).pack(fill="x", pady=10)
        ttk.Label(frame, text="Wallet addresses:", style="Section.TLabel").pack(anchor="w")
        for label, addr in [
            ("Smart Account (Base)", WALLET_BASE),
            ("Signer EOA (Base)",    SIGNER_EOA),
            ("BTC (Lightning)",      BTC_WALLET),
            ("XLM (Stellar)",        XLM_WALLET),
        ]:
            ttk.Label(frame, text=f"{label}:\n{addr}", style="TLabel").pack(anchor="w", pady=2)

    def _build_bounties_tab(self):
        cols = ("target","amount","status")
        self.btree = ttk.Treeview(self.tab_bounties, columns=cols, show="headings", height=12)
        for c, w in zip(cols, [300, 80, 600]):
            self.btree.heading(c, text=c.upper())
            self.btree.column(c, width=w, anchor="w")
        self.btree.pack(fill="both", expand=True, padx=5, pady=5)
        self.btree.tag_configure("high_value", background="#1a2e3d", foreground="#ffd700")
        self.btree.tag_configure("pending", background="#1a1d2e", foreground="#ffcc00")
        self.btree.tag_configure("zero", background="#0d0f1a", foreground="#888888")
        # Pre-populate with known targets
        for t, amt, status in FUNDED_TARGETS:
            tag = "high_value" if amt >= 50 else ("pending" if amt > 0 else "zero")
            self.btree.insert("", "end", values=(t, f"${amt:.2f}", status), tags=(tag,))

    def _build_email_tab(self):
        self.email_text = scrolledtext.ScrolledText(self.tab_email, wrap="word",
            bg="#1a1d2e", fg="#e0e0e0", font=("Consolas", 10), height=30)
        self.email_text.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_log_tab(self):
        self.log_text = scrolledtext.ScrolledText(self.tab_log, wrap="word",
            bg="#000000", fg="#00ff00", font=("Consolas", 9), height=30)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        ttk.Button(self.tab_log, text="Clear", command=self._clear_log).pack(anchor="e", padx=5, pady=2)

    # --------- Helpers ---------
    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _open_prs_url(self):
        self._open_url("https://github.com/pulls?q=author%3Amakar52nn2016-jpg+is%3Apr+is%3Aopen")

    def _load_existing_log(self):
        try:
            if LOG_FILE.exists():
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-300:]
                self.log_lines = [l.rstrip() for l in lines]
                self._refresh_log_view()
        except Exception:
            pass

    def _clear_log(self):
        self.log_lines = []
        self.log_text.delete("1.0", "end")

    def _refresh_log_view(self):
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(self.log_lines[-200:]))
        self.log_text.see("end")

    def log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]
        # Append to file
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception: pass
        # Update view
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def refresh_async(self):
        threading.Thread(target=self._refresh, daemon=True).start()

    def _refresh(self):
        self.status_var.set("🔄 Refreshing…")
        try:
            self._refresh_prs()
            self._refresh_wallet()
            self._refresh_email()
            self._calc_pending()
            self.status_var.set(f"✅ Last refresh: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            self.status_var.set(f"❌ Refresh error: {str(e)[:60]}")
        # Reset cycle timer
        self._cycle_count = 300

    def _refresh_prs(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.log("📋 Refreshing PR statuses…")
        for repo, num, bounty in WATCH_PRS:
            try:
                r = github_api(f"https://api.github.com/repos/{repo}/pulls/{num}")
                if r.get("error"):
                    self.tree.insert("", "end", values=(repo, num, "ERROR", "?", f"${bounty:.0f}", "?", "?", str(r.get("body","")[:30]), tags=("closed",))
                    continue
                state = r.get("state","?")
                merged = r.get("merged_at")
                title = r.get("title","")[:50]
                comments = r.get("comments", 0) + r.get("review_comments", 0)
                updated = r.get("updated_at","?")
                created = r.get("created_at","?")
                # Determine tag
                if merged:
                    tag = "merged"
                    state_disp = "MERGED ✅"
                    self.log(f"💰 MERGED: {repo}#{num} — bounty ${bounty:.2f}")
                elif state == "closed" and not merged:
                    tag = "closed"
                    state_disp = "CLOSED ❌"
                else:
                    tag = "open_pending"
                    state_disp = "OPEN ⏳"
                age = fmt_age(created)
                upd = fmt_age(updated)
                self.tree.insert("", "end",
                    values=(repo, num, title, state_disp, f"${bounty:.0f}", age, comments, upd),
                    tags=(tag,))
                # Check for new comments
                if comments > 0:
                    cs = github_api(f"https://api.github.com/repos/{repo}/issues/{num}/comments?per_page=3&sort=created&direction=desc")
                    if isinstance(cs, list) and cs:
                        last_c = cs[0]
                        last_user = last_c.get("user",{}).get("login","?")
                        if last_user not in ("makar52nn2016-jpg","github-actions[bot]","opirebot[bot]"):
                            self.log(f"💬 {repo}#{num}: last comment by @{last_user}: {last_c.get('body','')[:80]}")
            except Exception as e:
                self.log(f"⚠️ PR check err {repo}#{num}: {e}")

    def _refresh_wallet(self):
        self.log("💵 Refreshing wallet…")
        eth = rpc_balance(WALLET_BASE)
        eth_signer = rpc_balance(SIGNER_EOA)
        USDC = "0x833589fCD6eDb6E08f4c7DC8D5DCC7DD9B19D8aA"
        WETH = "0x4200000000000000000000000000000000000006"
        AERO = "0xA404d6dF0b5cF2Fe13D291a75d6F59cB0e0196c4"
        usdc = erc20_balance(USDC, WALLET_BASE)
        weth = erc20_balance(WETH, WALLET_BASE)
        aero = erc20_balance(AERO, WALLET_BASE)
        ETH_PRICE = 3200  # approx
        total_usd = (eth or 0)*ETH_PRICE + (eth_signer or 0)*ETH_PRICE + usdc/1e6 + weth/1e18*ETH_PRICE + aero/1e18
        if eth is not None:
            self.wallet_var.set(
                f"Smart account: {eth:.6f} ETH (${eth*ETH_PRICE:.2f})\n"
                f"Signer EOA:    {eth_signer or 0:.6f} ETH (${(eth_signer or 0)*ETH_PRICE:.2f})\n"
                f"USDC:          ${usdc/1e6:.4f}\n"
                f"WETH:          {weth/1e18:.6f} (${weth/1e18*ETH_PRICE:.2f})\n"
                f"AERO:          {aero/1e18:.4f}\n"
                f"TOTAL:         ${total_usd:.2f}"
            )
            self.log(f"💵 Wallet: ${total_usd:.2f} total (ETH {eth:.6f}, USDC ${usdc/1e6:.2f})")
        # Frantic estimate (no live API; use accumulated)
        self.frantic_var.set("Frantic: $0 confirmed paid (deliveries #128 $8, #129 $16 pending verification)")
        # Pending estimate
        pending_usd = sum(b for _, b, _ in FUNDED_TARGETS if b > 0)
        self.pending_var.set(f"💰 Pending PR payouts: ${pending_usd:.2f}  (when maintainers merge)")

    def _calc_pending(self):
        pass

    def _refresh_email(self):
        self.log("📧 Refreshing email…")
        self.email_text.delete("1.0", "end")
        emails = read_inbox(limit=8)
        for e in reversed(emails):
            self.email_text.insert("end", "─"*70 + "\n")
            self.email_text.insert("end", f"From: {e['from']}\n", "from")
            self.email_text.insert("end", f"Date: {e['date']}\n", "date")
            self.email_text.insert("end", f"Subj: {e['subject']}\n", "subj")
            self.email_text.insert("end", f"Body: {e['body'][:250]}\n", "body")
        self.log(f"📧 Loaded {len(emails)} recent emails")

    def _schedule_refresh(self, seconds):
        self._cycle_count = seconds
        self._tick()

    def _tick(self):
        if self._cycle_count > 0:
            m, s = divmod(self._cycle_count, 60)
            self.cycle_var.set(f"Next refresh: {m}:{s:02d}")
            self._cycle_count -= 1
        else:
            self.refresh_async()
            self._cycle_count = 300
        self.root.after(1000, self._tick)


def main():
    root = tk.Tk()
    app = BulldozerDashboard(root)
    root.mainloop()

if __name__ == "__main__":
    main()
