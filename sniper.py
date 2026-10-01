#!/usr/bin/env python3
"""Cloud Sniper v2 — autonomous bounty hunter + AgentBounties monitor.

Runs on GitHub Actions every 30 minutes. Each invocation:
  - Scans GitHub for fresh direct-payout bounties (label:bounty, wallet in body)
  - Checks AgentBounties API (NSPG13/agent-bounties) for ready_to_earn bounties with USDC payout
  - For GitHub bounties: files interest comments with wallet block
  - For AgentBounties: alerts TG with claim URL (user signs with MetaMask)
  - Records all claims/actions in sniper_state.json
  - Sends TG alert on each new bounty found

Wallets (in every claim comment):
  TON (USDT-on-TON): UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH
  MetaMask (ETH/USDC/USDT-on-ETH/Base): 0x30450A8B96535e4ee1897f1E59ff2556f6191bcc
  XLM: GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ
"""
import os
import json
import time
import logging
import requests
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("sniper")

GH_TOKEN = os.environ.get("GH_TOKEN", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "8838415681:AAGBgGauRZ-1sUF0lF0qniKoUcpcNIzuUHA")
TG_CHAT = os.environ.get("TG_CHAT", "322108803")

WALLETS = {
    "TON": "UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH",
    "MetaMask": "0x30450A8B96535e4ee1897f1E59ff2556f6191bcc",
    "XLM": "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ",
}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sniper_state.json")
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "User-Agent": "cloud-sniper-bot",
    "Accept": "application/vnd.github+json",
}

# Bounties already claimed (avoid duplicates)
ALREADY_CLAIMED = {
    "Scottcjn/rustchain-monitor#63", "Scottcjn/rustchain-bounties#254",
    "ULCproject/ulcproject.github.io#10", "ULCproject/ulcproject.github.io#1",
    "UniversalAviator420/bounty-sandbox#12", "dwebagents/AgentPipe#2120",
    "Heliobond/frontend#664", "Heliobond/frontend#665", "Heliobond/frontend#666",
    "Heliobond/frontend#668", "Heliobond/frontend#669", "Heliobond/frontend#670",
    "Heliobond/frontend#676", "ancore-org/ancore#1487", "StellarRoute/WaveFlow#71",
    "Soroban-Cookbook/Soroban_Cookbook_online#1006",
    "Soroban-Cookbook/Soroban_Cookbook_online#1007",
    "Soroban-Cookbook/Soroban_Cookbook_online#1008",
    "Soroban-Cookbook/Soroban_Cookbook_online#1009",
    "Soroban-Cookbook/Soroban_Cookbook_online#1010",
    "Soroban-Cookbook/Soroban_Cookbook_online#1011",
    "Soroban-Cookbook/Soroban_Cookbook_online#1012",
    "Soroban-Cookbook/Soroban_Cookbook_online#1013",
    "Soroban-Cookbook/Soroban_Cookbook_online#1017",
    "Soroban-Cookbook/Soroban_Cookbook_online#1018",
    "Soroban-Cookbook/Soroban_Cookbook_online#1019",
    "Soroban-Cookbook/Soroban_Cookbook_online#1020",
    "Soroban-Cookbook/Soroban_Cookbook_online#1021",
    "drydocs/meridian#982", "drydocs/meridian#983",
    "soroban-forge-labs/soroban-forge#488",
    "gear5labs/chenpilot-client#185", "gear5labs/chenpilot-client#186",
    "gear5labs/chenpilot-client#187", "gear5labs/chenpilot-client#189",
    "StellarCanary/ProtocolCanary-Action#306",
    "StellarCanary/ProtocolCanary-Fixtures#241", "StellarCanary/ProtocolCanary-Fixtures#242",
    "maaltarifi97-maker/aioa-playground#1",
}


def tg_send(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.warning("tg_send: %s", e)
        return False


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"claimed": [], "last_scan": 0, "agentbounty_seen": []}
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
            # Ensure all keys exist
            s.setdefault("claimed", [])
            s.setdefault("last_scan", 0)
            s.setdefault("agentbounty_seen", [])
            return s
    except Exception:
        return {"claimed": [], "last_scan": 0, "agentbounty_seen": []}


def save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception as e:
        log.warning("save_state: %s", e)


def wallet_block():
    return (
        f"\n\n### Payout wallet\n"
        f"**TON (USDT-on-TON):** `{WALLETS['TON']}`\n"
        f"**MetaMask (ETH/USDC/USDT-on-ETH/Base):** `{WALLETS['MetaMask']}`\n"
        f"**XLM:** `{WALLETS['XLM']}`\n"
        f"Pay in whichever rail you prefer."
    )


# ============== GitHub bounty scan ==============
def scan_github_bounties(state):
    """Search GitHub for fresh direct-payout bounties."""
    seen = set(state.get("claimed", []))
    new_candidates = []

    queries = [
        'label:bounty state:open is:issue no:assignee wallet in:body',
        'label:bounty state:open is:issue no:assignee payout in:body',
        'label:bounty state:open is:issue no:assignee "Bounty:" in:title',
    ]

    for q in queries:
        try:
            r = requests.get(
                "https://api.github.com/search/issues",
                params={"q": q, "per_page": 20, "sort": "created", "order": "desc"},
                headers=HEADERS, timeout=30,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            for item in data.get("items", [])[:20]:
                repo = '/'.join(item['repository_url'].split('/')[-2:])
                num = item['number']
                key = f"{repo}#{num}"
                if key in seen or key in ALREADY_CLAIMED:
                    continue
                if 'pull_request' in item:
                    continue
                new_candidates.append({
                    "repo": repo, "num": num, "key": key,
                    "title": item["title"][:80],
                    "url": item["html_url"],
                    "body_excerpt": (item.get("body", "") or "")[:200],
                    "created": item["created_at"][:10],
                })
            time.sleep(2)
        except Exception as e:
            log.warning("github scan query failed: %s", e)

    # Deduplicate
    seen_keys = set()
    unique = []
    for c in new_candidates:
        if c["key"] in seen_keys:
            continue
        seen_keys.add(c["key"])
        unique.append(c)

    return unique


def check_existing_prs(repo, num):
    """Check if there are already open PRs for this issue."""
    try:
        r = requests.get(
            "https://api.github.com/search/issues",
            params={"q": f"repo:{repo} is:pr is:open {num} in:body", "per_page": 5},
            headers=HEADERS, timeout=15,
        )
        if r.status_code != 200:
            return False, 0
        count = r.json().get("total_count", 0)
        return count > 0, count
    except Exception:
        return False, 0


def file_interest_comment(repo, num, title, body_excerpt):
    """Post polite interest comment with wallet block."""
    comment_body = (
        f"Interested in taking this on. Reading the description — the acceptance criteria is clear.\n\n"
        f"Once assigned, I'll deliver within ETA. If this is a direct-payout bounty (no "
        f"signup needed), my wallet block is below; otherwise I'll go through whatever "
        f"application flow the maintainer prefers.{wallet_block()}"
    )
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/issues/{num}/comments",
            headers=HEADERS, json={"body": comment_body}, timeout=15,
        )
        return r.status_code == 201
    except Exception as e:
        log.warning("file_interest_comment: %s", e)
        return False


# ============== AgentBounties (NSPG13) — USDC on Base ==============
def scan_agentbounties(state):
    """Scan AgentBounties API for ready_to_earn bounties with USDC payout."""
    seen = set(state.get("agentbounty_seen", []))
    new_bounties = []

    try:
        r = requests.get(
            "https://api.agentbounties.app/v1/github/bounty-discovery-v1",
            timeout=30,
        )
        if r.status_code != 200:
            log.warning("agentbounties API failed: %d", r.status_code)
            return []
        data = r.json()
        items = data.get("items", [])
        ready = [b for b in items if b.get("ready_to_earn")]
        for b in ready:
            bounty_id = b.get("bounty_id") or b.get("discovery_id") or b.get("bounty_contract")
            if bounty_id in seen:
                continue
            try:
                reward_raw = b.get("reward_usdc_base_units", "0")
                try:
                    reward = int(reward_raw) / 1e6
                except (ValueError, TypeError):
                    reward = float(reward_raw) / 1e6
            except Exception:
                reward = 0
            new_bounties.append({
                "bounty_id": bounty_id,
                "title": b.get("title", "")[:80],
                "reward_usdc": reward,
                "public_url": b.get("public_url", ""),
                "source_url": b.get("source_url", ""),
                "lifecycle_state": b.get("lifecycle_state", ""),
            })
    except Exception as e:
        log.warning("agentbounties scan failed: %s", e)
        return []

    return new_bounties


# ============== Main ==============
def main():
    log.info("Cloud Sniper v2 start")
    state = load_state()

    # === GitHub bounties ===
    gh_candidates = scan_github_bounties(state)
    log.info("GitHub: %d fresh bounty candidates", len(gh_candidates))

    if gh_candidates:
        gh_candidates.sort(key=lambda x: x["created"], reverse=True)
        claimed_this_cycle = []
        for c in gh_candidates[:5]:
            has_prs, pr_count = check_existing_prs(c["repo"], c["num"])
            if has_prs:
                log.info("Skip %s — already has %d PRs", c["key"], pr_count)
                continue
            success = file_interest_comment(c["repo"], c["num"], c["title"], c["body_excerpt"])
            if success:
                claimed_this_cycle.append(c)
                state["claimed"].append(c["key"])
                tg_send(
                    f"🎯 GitHub Bounty: NEW CLAIM\n\n"
                    f"📋 {c['repo']}#{c['num']}\n"
                    f"Title: {c['title']}\n"
                    f"Created: {c['created']}\n"
                    f"URL: {c['url']}\n\n"
                    f"Posted interest comment with wallet block.\n"
                    f"Wallets:\n"
                    f"  TON: {WALLETS['TON']}\n"
                    f"  MetaMask: {WALLETS['MetaMask']}\n"
                    f"  XLM: {WALLETS['XLM']}"
                )
            time.sleep(3)

    # === AgentBounties (USDC on Base) ===
    ab_bounties = scan_agentbounties(state)
    log.info("AgentBounties: %d ready_to_earn bounties", len(ab_bounties))

    if ab_bounties:
        # Sort by reward descending — biggest first
        ab_bounties.sort(key=lambda x: -x["reward_usdc"])
        for b in ab_bounties[:3]:  # Top 3 by reward
            state["agentbounty_seen"].append(b["bounty_id"])
            tg_send(
                f"💰 AgentBounties: READY TO EARN\n\n"
                f"📋 {b['title']}\n"
                f"Reward: ${b['reward_usdc']:.2f} USDC (on Base)\n"
                f"State: {b['lifecycle_state']}\n"
                f"Claim URL: {b['public_url']}\n"
                f"Source: {b['source_url'] or 'n/a'}\n\n"
                f"💡 Sign with MetaMask (Base) to claim → {WALLETS['MetaMask']}"
            )

    if not gh_candidates and not ab_bounties:
        tg_send(f"🔭 Cloud Sniper: scan complete, no fresh direct-payout bounties "
                f"in this cycle. Will retry in 30 min.")

    state["last_scan"] = time.time()
    save_state(state)
    log.info("Sniper cycle done")


if __name__ == "__main__":
    main()
