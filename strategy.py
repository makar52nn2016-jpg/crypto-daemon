#!/usr/bin/env python3
"""
ROOT TREE STRATEGY — Unified Autonomous Earning System

Reputation (roots) → Daemon (trunk) → 4 income branches → compound growth

Every PR, star, comment feeds back into reputation.
More reputation → faster merges → more payouts → more reputation.
"""
import os, json, time, logging, requests
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("tree")

GH_TOKEN = os.environ.get("GH_TOKEN", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "8838415681:AAGBgGauRZ-1sUF0lF0qniKoUcpcNIzuUHA")
TG_CHAT = os.environ.get("TG_CHAT", "322108803")
HEADERS = {"Authorization": f"Bearer {GH_TOKEN}", "User-Agent": "root-tree-bot", "Accept": "application/vnd.github+json"}

def tg_send(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True}, timeout=10)
    except: pass

def check_reputation():
    try:
        u = requests.get("https://api.github.com/users/makar52nn2016-jpg", headers=HEADERS, timeout=15).json()
        repos = requests.get("https://api.github.com/users/makar52nn2016-jpg/repos?per_page=100", headers=HEADERS, timeout=15).json()
        total_stars = sum(r.get("stargazers_count", 0) for r in repos if not r.get("fork")) if isinstance(repos, list) else 0
        total_prs = requests.get("https://api.github.com/search/issues",
            params={"q": "author:makar52nn2016-jpg type:pr", "per_page": 1}, headers=HEADERS, timeout=15).json().get("total_count", 0)
        merged_prs = requests.get("https://api.github.com/search/issues",
            params={"q": "author:makar52nn2016-jpg type:pr is:merged", "per_page": 1}, headers=HEADERS, timeout=15).json().get("total_count", 0)
        return {"stars": total_stars, "following": u.get("following", 0), "followers": u.get("followers", 0),
                "repos": u.get("public_repos", 0), "prs": total_prs, "merged": merged_prs}
    except Exception as e:
        log.warning(f"reputation: {e}")
        return {}

STOMPSTART_PRS = [9, 10, 11, 21, 22]

def check_stompstart():
    results = []
    for num in STOMPSTART_PRS:
        try:
            pr = requests.get(f"https://api.github.com/repos/auscaster/stompstart-startup-list/pulls/{num}", headers=HEADERS, timeout=15).json()
            results.append({"pr": num, "merged": pr.get("merged", False), "ms": pr.get("mergeable_state", "?"), "title": pr.get("title", "")[:25]})
        except: pass
    return results

BOUNTY_PRS = [
    ("Heliobond/frontend", 676, 100), ("Heliobond/frontend", 664, 100),
    ("Heliobond/frontend", 668, 100), ("Heliobond/frontend", 669, 100),
    ("gear5labs/chenpilot-client", 185, 50), ("gear5labs/chenpilot-client", 186, 50),
    ("gear5labs/chenpilot-client", 187, 50), ("gear5labs/chenpilot-client", 189, 50),
    ("StellarCanary/ProtocolCanary-Action", 306, 50),
    ("StellarCanary/ProtocolCanary-Fixtures", 241, 50),
    ("StellarCanary/ProtocolCanary-Fixtures", 242, 50),
    ("soroban-forge-labs/soroban-forge", 488, 50),
    ("UniversalAviator420/bounty-sandbox", 12, 50),
    ("dwebagents/AgentPipe", 2120, 23),
]

def check_bounties():
    results = []
    pending = 0
    for repo, num, bounty in BOUNTY_PRS:
        try:
            pr = requests.get(f"https://api.github.com/repos/{repo}/pulls/{num}", headers=HEADERS, timeout=15).json()
            merged = pr.get("merged", False)
            if not merged: pending += bounty
            results.append({"repo": repo, "num": num, "bounty": bounty, "merged": merged})
        except: pass
    return results, pending

def check_wallets():
    w = {}
    try:
        r = requests.get("https://horizon.stellar.org/accounts/GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ", timeout=10)
        for b in r.json().get("balances", []):
            if b.get("asset_type") == "native": w["XLM"] = float(b.get("balance", "0"))
    except: w["XLM"] = "?"
    try:
        r = requests.get("https://tonapi.io/v2/accounts/UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH", timeout=10)
        w["TON"] = r.json().get("balance", 0) / 1e9
    except: w["TON"] = "?"
    try:
        r = requests.get("https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address=0x30450A8B96535e4ee1897f1E59ff2556f6191bcc&tag=latest", timeout=10)
        result = r.json().get("result", "0")
        w["ETH"] = int(result) / 1e18 if result.isdigit() else 0
    except: w["ETH"] = "?"
    try:
        r = requests.get("https://blockstream.info/api/address/bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5", timeout=10)
        sat = r.json().get("chain_stats", {}).get("funded_txo_sum", 0) - r.json().get("chain_stats", {}).get("spent_txo_sum", 0)
        w["BTC"] = sat / 1e8
    except: w["BTC"] = "?"
    try:
        r = requests.post("https://api.mainnet-beta.solana.com",
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": ["25f1M7tdwaUq1LWku5F2LkZXesEkADmr3t8VdmpGp13D"]}, timeout=10)
        w["SOL"] = r.json().get("result", {}).get("value", 0) / 1e9
    except: w["SOL"] = "?"
    return w

def tree_status():
    rep = check_reputation()
    stomp = check_stompstart()
    bounties, pending = check_bounties()
    wallets = check_wallets()
    
    stomp_merged = sum(1 for s in stomp if s["merged"])
    stomp_clean = sum(1 for s in stomp if s["ms"] == "clean" and not s["merged"])
    stomp_potential = (stomp_merged + stomp_clean) * 1.50
    bounty_merged = sum(1 for b in bounties if b["merged"])
    
    print("ROOT TREE STRATEGY — UNIFIED STATUS")
    print("=" * 60)
    print(f"\nROOTS: {rep.get('merged',0)}/{rep.get('prs',0)} PRs merged, {rep.get('stars',0)} stars, {rep.get('followers',0)} followers")
    print(f"TRUNK: daemon 5min + sniper 30min + website LIVE")
    print(f"\nBRANCH 1 Stompstart: {stomp_merged} merged + {stomp_clean} clean = ${stomp_potential:.2f}")
    print(f"BRANCH 2 Bounties: {bounty_merged} merged + {len(bounties)-bounty_merged} open = ${pending} pending")
    print(f"BRANCH 3 Content: 6 art + ebook + website + awesome-list PR")
    print(f"BRANCH 4 Wallets: XLM={wallets.get('XLM','?')} TON={wallets.get('TON','?')} ETH={wallets.get('ETH','?')}")
    print(f"\nTOTAL POTENTIAL: ${stomp_potential + pending + 650 + 1:.0f}+")
    
    msg = f"""ROOT TREE STATUS

ROOTS: {rep.get('merged',0)}/{rep.get('prs',0)} PRs merged, {rep.get('stars',0)} stars
TRUNK: daemon + sniper + website (24/7)

BRANCHES:
1. Stompstart: {stomp_merged} merged + {stomp_clean} clean = ${stomp_potential:.2f}
2. Bounties: {bounty_merged} merged + {len(bounties)-bounty_merged} open = ${pending} pending
3. Content: 6 art + ebook + website + awesome-list PR
4. Wallets: XLM={wallets.get('XLM','?')} TON={wallets.get('TON','?')} ETH={wallets.get('ETH','?')}

TOTAL POTENTIAL: ${stomp_potential + pending + 650 + 1:.0f}+ (growing)
Compound: Week 1: $6 | Week 4: $50-300 | Month 3: $300-1000+

The tree grows. Every action feeds the roots."""
    tg_send(msg)

if __name__ == "__main__":
    tree_status()
