#!/usr/bin/env python3
"""Crypto Daemon — 24/7 autonomous earning system (GitHub Actions edition).

Runs on a cron schedule every 5 minutes. Each invocation:
  - Checks XLM/ETH/BTC/SOL wallet balances → alerts on incoming funds (RU).
  - Polls open PRs for merges, new comments, review changes → alerts in RU.
  - Scans for new bounties across multiple repos.
  - Posts a heartbeat to TG every 6 hours so the user knows the daemon is alive.

Designed to be stateless across invocations: writes state to ./state.json which is
committed by the GitHub Action after each run.
"""
import os
import json
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("daemon")

GH_TOKEN = os.environ.get("GH_TOKEN", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "8838415681:AAGBgGauRZ-1sUF0lF0qniKoUcpcNIzuUHA")
TG_CHAT = os.environ.get("TG_CHAT", "322108803")
XLM_ADDR = "GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ"
ETH_ADDR = "0x30450A8B96535e4ee1897f1E59ff2556f6191bcc"
BTC_ADDR = "bc1q0f99e8pcp6n6wgfv09kyea3getra0qwme98xm5"
SOL_ADDR = "25f1M7tdwaUq1LWku5F2LkZXesEkADmr3t8VdmpGp13D"
TRX_ADDR = "TNQdBautGuPihGXqwNJYLwHWLjVHs2p4A8"

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# All tracked PRs: (repo, pr_number, bounty_usd, label)
PRS = [
    ("UniversalAviator420/bounty-sandbox", 12, 50, "bounty-sandbox README"),
    ("dwebagents/AgentPipe", 2120, 23, "AgentPipe contributors"),
    ("Heliobond/frontend", 664, 100, "Node 22 bump"),
    ("Heliobond/frontend", 665, 100, "stellar.expert URLs"),
    ("Heliobond/frontend", 668, 100, "invest routing fix"),
    ("Heliobond/frontend", 669, 100, "yield edge-trigger alerts"),
    ("Heliobond/frontend", 676, 100, "registry decoder"),
    ("ancore-org/ancore", 1487, 0, "retry wrapper"),
    ("StellarRoute/WaveFlow", 71, 100, "CONTRIBUTING.md + Wave bounty workflow"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1006, 50, "contract-ids key-handling"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1007, 50, "authorization key+net guards"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1008, 50, "authorization-trees key+net guards"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1009, 50, "setup-linux key-handling"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1010, 50, "token-audit unaudited notice"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1011, 50, "fundamentals unaudited notice"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1012, 50, "upgrade-checklist unaudited notice"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1013, 50, "defi-patterns unaudited notice"),
]

HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "User-Agent": "crypto-daemon-bot",
    "Accept": "application/vnd.github+json",
}


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "prev_xlm": 9.8081229, "prev_eth": 0.0, "prev_btc": 0.0, "prev_sol": 0.0,
            "prev_pr_states": {}, "last_heartbeat": 0, "last_comment_seen": {},
            "seen_bounties": {},
        }
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "prev_xlm": 9.8081229, "prev_eth": 0.0, "prev_btc": 0.0, "prev_sol": 0.0,
            "prev_pr_states": {}, "last_heartbeat": 0, "last_comment_seen": {},
            "seen_bounties": {},
        }


def save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f, indent=2)
    except Exception as e:
        log.warning("save_state: %s", e)


def tg_send(text, parse_mode=None):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": text, "parse_mode": parse_mode,
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        log.warning("tg_send: %s", e)
        return False


# ============== WALLET MONITOR ==============
def check_xlm(prev):
    try:
        r = requests.get(f"https://horizon.stellar.org/accounts/{XLM_ADDR}", timeout=10)
        if r.status_code != 200:
            return prev
        for b in r.json().get("balances", []):
            if b.get("asset_type") == "native":
                bal = float(b.get("balance", "0"))
                if bal > prev + 0.001:
                    delta = bal - prev
                    tg_send(
                        f"💰 XLM INCOMING: +{delta:.4f} XLM\n"
                        f"Баланс: {prev:.4f} → {bal:.4f} XLM\n"
                        f"Адрес: {XLM_ADDR}\n"
                        f"https://stellar.expert/explorer/public/account/{XLM_ADDR}"
                    )
                    return bal
                return bal
    except Exception as e:
        log.warning("xlm: %s", e)
    return prev


def check_eth(prev):
    try:
        r = requests.get(
            f"https://api.etherscan.io/api?module=account&action=balance&address={ETH_ADDR}&tag=latest",
            timeout=10,
        )
        if r.status_code == 200:
            wei = int(r.json().get("result", "0") or "0")
            bal = wei / 1e18
            if bal > prev + 0.0001:
                delta = bal - prev
                tg_send(
                    f"💰 ETH INCOMING: +{delta:.6f} ETH\n"
                    f"Баланс: {prev:.6f} → {bal:.6f} ETH\n"
                    f"Адрес: {ETH_ADDR}\n"
                    f"https://etherscan.io/address/{ETH_ADDR}"
                )
                return bal
            return bal
    except Exception as e:
        log.warning("eth: %s", e)
    return prev


def check_btc(prev):
    try:
        r = requests.get(f"https://blockstream.info/api/address/{BTC_ADDR}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            sat = (data.get("chain_stats", {}).get("funded_txo_sum", 0) -
                   data.get("chain_stats", {}).get("spent_txo_sum", 0))
            bal = sat / 1e8
            if bal > prev + 0.00001:
                delta = bal - prev
                tg_send(
                    f"💰 BTC INCOMING: +{delta:.8f} BTC\n"
                    f"Баланс: {prev:.8f} → {bal:.8f} BTC\n"
                    f"Адрес: {BTC_ADDR}"
                )
                return bal
            return bal
    except Exception as e:
        log.warning("btc: %s", e)
    return prev


def check_sol(prev):
    try:
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance",
                  "params": [SOL_ADDR]},
            timeout=10,
        )
        if r.status_code == 200:
            lamports = r.json().get("result", {}).get("value", 0)
            bal = lamports / 1e9
            if bal > prev + 0.001:
                delta = bal - prev
                tg_send(
                    f"💰 SOL INCOMING: +{delta:.6f} SOL\n"
                    f"Баланс: {prev:.6f} → {bal:.6f} SOL\n"
                    f"Адрес: {SOL_ADDR}"
                )
                return bal
            return bal
    except Exception as e:
        log.warning("sol: %s", e)
    return prev


def check_wallets(state):
    state["prev_xlm"] = check_xlm(state.get("prev_xlm", 9.8081229))
    state["prev_eth"] = check_eth(state.get("prev_eth", 0.0))
    state["prev_btc"] = check_btc(state.get("prev_btc", 0.0))
    state["prev_sol"] = check_sol(state.get("prev_sol", 0.0))
    return state


# ============== PR TRACKER ==============
def check_prs(state):
    seen = state.get("last_comment_seen", {})
    pr_states = state.get("prev_pr_states", {})
    total_potential = 0

    for repo, num, bounty, label in PRS:
        try:
            pr = requests.get(
                f"https://api.github.com/repos/{repo}/pulls/{num}",
                headers=HEADERS, timeout=15,
            ).json()
            if "title" not in pr:
                log.warning("PR fetch failed %s#%s: %s", repo, num, pr)
                continue

            state_key = f"{repo}#{num}"
            was_merged = pr_states.get(state_key, {}).get("merged", False)
            now_merged = pr.get("merged", False)

            # 1) MERGE DETECTED → celebrate
            if now_merged and not was_merged:
                if bounty > 0:
                    tg_send(
                        f"🎉 PR СМЕРЖЕН: {repo}#{num}\n"
                        f"Задача: {label}\n"
                        f"Награда: ${bounty}\n"
                        f"https://github.com/{repo}/pull/{num}\n\n"
                        f"Ждем payout (1-14 дней для Stellar Wave через drips.network)"
                    )
                else:
                    tg_send(
                        f"✅ PR СМЕРЖЕН: {repo}#{num} ({label})\n"
                        f"https://github.com/{repo}/pull/{num}"
                    )

            if not now_merged:
                total_potential += bounty

            # 2) NEW COMMENTS
            comments = requests.get(
                f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                headers=HEADERS, timeout=15,
            ).json()
            last_seen_id = seen.get(state_key, 0)
            new_comments = [c for c in comments if c.get("id", 0) > last_seen_id]
            other_comments = [c for c in new_comments
                              if c.get("user", {}).get("login") != "makar52nn2016-jpg"]
            if other_comments:
                last = other_comments[-1]
                who = last["user"]["login"]
                body = (last.get("body", "") or "")[:300]
                if "[bot]" not in who:
                    tg_send(
                        f"💬 Новый комментарий {repo}#{num}:\n"
                        f"@{who}: {body}\n"
                        f"https://github.com/{repo}/pull/{num}"
                    )
                if comments:
                    seen[state_key] = max(c.get("id", 0) for c in comments)

            # 3) REVIEW STATE CHANGES
            reviews = requests.get(
                f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
                headers=HEADERS, timeout=15,
            ).json()
            if reviews:
                last_review = reviews[-1]
                review_state = last_review.get("state")
                review_by = last_review.get("user", {}).get("login", "?")
                prev_review_state = pr_states.get(state_key, {}).get("review_state")
                if review_state != prev_review_state and review_by != "makar52nn2016-jpg":
                    emoji = {"APPROVED": "✅", "CHANGES_REQUESTED": "⚠️", "COMMENTED": "💬"}.get(review_state, "📝")
                    tg_send(
                        f"{emoji} {repo}#{num}: review {review_state} by @{review_by}\n"
                        f"Задача: {label} (${bounty})\n"
                        f"https://github.com/{repo}/pull/{num}"
                    )

            # 4) MERGEABLE STATE
            mergeable = pr.get("mergeable")
            mergeable_state = pr.get("mergeable_state")
            prev_ms = pr_states.get(state_key, {}).get("mergeable_state")
            if mergeable_state == "dirty" and prev_ms != "dirty":
                tg_send(
                    f"⚠️ КОНФЛИКТ: {repo}#{num} ({label}) — dirty\n"
                    f"Нужен rebase! https://github.com/{repo}/pull/{num}"
                )

            pr_states[state_key] = {
                "merged": now_merged,
                "state": pr.get("state"),
                "mergeable": mergeable,
                "mergeable_state": mergeable_state,
                "title": pr.get("title", ""),
                "review_state": reviews[-1].get("state") if reviews else None,
                "updated_at": pr.get("updated_at"),
            }
        except Exception as e:
            log.warning("PR %s#%s: %s", repo, num, e)

    state["prev_pr_states"] = pr_states
    state["last_comment_seen"] = seen
    return total_potential


# ============== BOUNTY SCANNER ==============
BOUNTY_REPOS = [
    "stellar/stellar-demo-wallet",
    "starscale-network/stellar-developer-bounties",
    "auscaster/frantic-board",
    "Heliobond/frontend",
    "dwebagents/AgentPipe",
    "UniversalAviator420/bounty-sandbox",
    "ancore-org/ancore",
]


def scan_bounties(state):
    seen_issues = state.setdefault("seen_bounties", {})
    found_new = 0

    for repo in BOUNTY_REPOS:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{repo}/issues",
                params={"state": "open", "labels": "bounty", "per_page": 30},
                headers=HEADERS, timeout=15,
            )
            if r.status_code != 200:
                continue
            for issue in r.json():
                if "pull_request" in issue:
                    continue
                num = issue.get("number")
                key = f"{repo}#{num}"
                if key not in seen_issues:
                    seen_issues[key] = {"title": issue.get("title"), "url": issue.get("html_url")}
                    found_new += 1
                    labels = [l["name"] for l in issue.get("labels", [])]
                    assignee = issue.get("assignee")
                    if assignee is None:
                        tg_send(
                            f"🎯 НОВЫЙ BOUNTY: {repo}#{num}\n"
                            f"Тема: {issue.get('title', '')[:80]}\n"
                            f"Labels: {', '.join(labels[:5])}\n"
                            f"Self-assignable: ДА\n"
                            f"{issue.get('html_url')}"
                        )
        except Exception as e:
            log.warning("bounty scan %s: %s", repo, e)
    return found_new


# ============== HEARTBEAT ==============
def maybe_heartbeat(state):
    now = time.time()
    last = state.get("last_heartbeat", 0)
    if now - last > 6 * 3600:
        state["last_heartbeat"] = now
        merged_count = sum(1 for k, v in state.get("prev_pr_states", {}).items() if v.get("merged"))
        total_potential = sum(b for _, _, b, _ in PRS
                              if not state["prev_pr_states"].get(f"{_[0]}#{_[1]}", {}).get("merged"))
        tg_send(
            f"💓 Daemon живой (GitHub Actions)\n"
            f"PRs merged: {merged_count}/{len(PRS)}\n"
            f"Potential outstanding: ${total_potential}\n"
            f"XLM: {state.get('prev_xlm', 0):.4f} | ETH: {state.get('prev_eth', 0):.6f}\n"
            f"BTC: {state.get('prev_btc', 0):.8f} | SOL: {state.get('prev_sol', 0):.6f}"
        )
    return state


# ============== MAIN ==============
def main():
    log.info("Daemon start")
    state = load_state()
    log.info("State loaded: keys=%s", list(state.keys()))

    state = check_wallets(state)
    total_potential = check_prs(state)
    found_new = scan_bounties(state)
    state = maybe_heartbeat(state)

    save_state(state)
    log.info("Daemon end. Open PRs potential: $%d, new bounties: %d", total_potential, found_new)


if __name__ == "__main__":
    main()
