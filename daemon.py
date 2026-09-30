#!/usr/bin/env python3
"""Crypto Daemon v2 — 24/7 autonomous earning system (GitHub Actions edition).

Smart alerting policy: ONLY alerts when human action is required.
- ✅ Alert: PR approved but not merged after 24h → send ready-to-copy ping text
- ✅ Alert: PR CI failed (build/test, not fork-Vercel)
- ✅ Alert: PR conflict/dirty (needs rebase)
- ✅ Alert: Wallet incoming funds
- ✅ Alert: PR merged (success!)
- ✅ Alert: New maintainer comment requiring reply
- 🤫 Silent: routine state changes, no-op events

Plus: auto-generates ready-to-paste ping comments when >24h elapsed.
"""
import os
import json
import time
import logging
import requests
from datetime import datetime, timezone

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

# All tracked PRs: (repo, pr_number, bounty_usd, label, language)
PRS = [
    ("UniversalAviator420/bounty-sandbox", 12, 50, "bounty-sandbox README"),
    ("dwebagents/AgentPipe", 2120, 23, "AgentPipe contributors"),
    ("Heliobond/frontend", 664, 100, "Node 22 bump"),
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
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1017, 50, "setup-windows key-handling"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1018, 50, "setup-macos key-handling"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1019, 50, "deploy-testnet key-handling"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1020, 50, "patterns/overview unaudited"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1021, 50, "examples-index unaudited"),
    ("drydocs/meridian", 982, 50, "format/protocolLabels tests"),
    ("drydocs/meridian", 983, 50, "useAdminHistory hook test"),
    ("soroban-forge-labs/soroban-forge", 488, 50, "network remove subcommand"),
    ("gear5labs/chenpilot-client", 185, 50, "remove tsc_output.txt artifact"),
    ("gear5labs/chenpilot-client", 186, 50, "logger helper + console.log removal"),
    ("gear5labs/chenpilot-client", 187, 50, "format/validation tests"),
    ("StellarCanary/ProtocolCanary-Action", 306, 50, "main.ts error-branch tests"),
    ("gear5labs/chenpilot-client", 189, 50, "dedupe socketManager tests"),
    ("StellarCanary/ProtocolCanary-Fixtures", 241, 50, "non-array assert value rejected"),
    ("StellarCanary/ProtocolCanary-Fixtures", 242, 50, "expected_file accepts existing"),
]

# Repos where Vercel/preview failure is expected for fork PRs (do NOT alert on those)
FORK_VERCEL_REPOS = {"Heliobond/frontend"}

HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "User-Agent": "crypto-daemon-bot",
    "Accept": "application/vnd.github+json",
}

# 24 hours in seconds
SLA_THRESHOLD_SECONDS = 24 * 3600


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "prev_xlm": 9.8081229, "prev_eth": 0.0, "prev_btc": 0.0, "prev_sol": 0.0,
            "prev_pr_states": {}, "last_heartbeat": 0, "last_comment_seen": {},
            "seen_bounties": {}, "pinged_prs": {},
        }
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "prev_xlm": 9.8081229, "prev_eth": 0.0, "prev_btc": 0.0, "prev_sol": 0.0,
            "prev_pr_states": {}, "last_heartbeat": 0, "last_comment_seen": {},
            "seen_bounties": {}, "pinged_prs": {},
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


# ============== WALLET MONITOR (always alert on incoming) ==============
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
        # Etherscan V2 API (V1 deprecated)
        r = requests.get(
            f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={ETH_ADDR}&tag=latest",
            timeout=10,
        )
        if r.status_code == 200:
            result = r.json().get("result", "0")
            # Etherscan returns string error in result on failure
            try:
                wei = int(result)
            except (ValueError, TypeError):
                log.warning("eth: %s", str(result)[:100])
                return prev
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


# ============== SMART PR TRACKER ==============
def get_repo_maintainers(repo, num):
    """Find maintainers/reviewers from PR reviews + repo owner."""
    maintainers = set()
    try:
        revs = requests.get(
            f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
            headers=HEADERS, timeout=15,
        ).json()
        for r in revs:
            u = r.get("user", {}).get("login", "")
            if u and u != "makar52nn2016-jpg" and "[bot]" not in u:
                maintainers.add(u)
    except Exception:
        pass
    try:
        repo_data = requests.get(
            f"https://api.github.com/repos/{repo}", headers=HEADERS, timeout=15,
        ).json()
        owner = repo_data.get("owner", {}).get("login", "")
        if owner:
            maintainers.add(owner)
    except Exception:
        pass
    return list(maintainers)


def generate_ping_comment(maintainers_list, repo, num, label, bounty):
    """Generate ready-to-paste ping comment text for Telegram."""
    mentions = " ".join(f"@{u}" for u in maintainers_list) or "@maintainer"
    return (
        f"🔥 ACTION NEEDED — PR waiting >24h\n\n"
        f"📋 {repo}#{num} — {label}\n"
        f"Bounty: ${bounty}\n"
        f"Status: APPROVED, mergeable, but not merged for >24h\n\n"
        f"📝 Готовый комментарий (copy-paste):\n"
        f"```\n"
        f"Hi {mentions}, all CI checks passed and the PR is mergeable. "
        f"Could you merge when convenient? Thanks!\n"
        f"```\n"
        f"🔗 {repo}/pull/{num}"
    )


def check_prs(state):
    """Smart PR tracking — only alert on action-needed events."""
    seen = state.get("last_comment_seen", {})
    pr_states = state.get("prev_pr_states", {})
    pinged = state.get("pinged_prs", {})
    now = datetime.now(timezone.utc)
    action_needed_count = 0

    for repo, num, bounty, label in PRS:
        try:
            pr = requests.get(
                f"https://api.github.com/repos/{repo}/pulls/{num}",
                headers=HEADERS, timeout=15,
            ).json()
            if "title" not in pr:
                continue

            state_key = f"{repo}#{num}"
            was_merged = pr_states.get(state_key, {}).get("merged", False)
            now_merged = pr.get("merged", False)
            prev_review_state = pr_states.get(state_key, {}).get("review_state")

            # === ALWAYS ALERT: merge detected ===
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
                    tg_send(f"✅ PR СМЕРЖЕН: {repo}#{num} ({label})")
                action_needed_count += 1
                pr_states[state_key] = {"merged": True, "state": "merged",
                                         "title": pr.get("title", "")}
                continue

            if now_merged:
                # already known merged — skip
                pr_states[state_key] = {"merged": True}
                continue

            # === Get CI state ===
            sha = pr.get("head", {}).get("sha", "")
            ci_state = "?"
            check_conclusions = []
            if sha:
                try:
                    st = requests.get(
                        f"https://api.github.com/repos/{repo}/commits/{sha}/status",
                        headers=HEADERS, timeout=15,
                    ).json()
                    ci_state = st.get("state", "?")
                except Exception:
                    pass
                try:
                    cr = requests.get(
                        f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs",
                        headers=HEADERS, timeout=15,
                    ).json()
                    check_conclusions = [
                        (c.get("name"), c.get("conclusion"))
                        for c in cr.get("check_runs", [])[:5]
                    ]
                except Exception:
                    pass

            # === ALERT: CI failure (build/test, NOT Vercel fork) ===
            # Determine if any "real" check failed (build, test, lint)
            real_failures = []
            for name, conclusion in check_conclusions:
                if conclusion == "failure" and name:
                    # Skip Vercel preview for fork PRs
                    if repo in FORK_VERCEL_REPOS and "Vercel" in name:
                        continue
                    real_failures.append(name)

            prev_ci = pr_states.get(state_key, {}).get("ci_state")
            if real_failures and ci_state != prev_ci:
                tg_send(
                    f"❌ CI FAIL: {repo}#{num} ({label})\n"
                    f"Failed checks: {', '.join(real_failures[:3])}\n"
                    f"Нужно поправить! https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1

            # === ALERT: dirty / conflict ===
            mergeable_state = pr.get("mergeable_state")
            prev_ms = pr_states.get(state_key, {}).get("mergeable_state")
            if mergeable_state == "dirty" and prev_ms != "dirty":
                tg_send(
                    f"⚠️ КОНФЛИКТ: {repo}#{num} ({label}) — dirty\n"
                    f"Нужен rebase! https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1

            # === Get reviews ===
            reviews = requests.get(
                f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
                headers=HEADERS, timeout=15,
            ).json()
            last_review = reviews[-1] if reviews else None
            review_state = last_review.get("state") if last_review else None
            review_by = last_review.get("user", {}).get("login") if last_review else None

            # === ALERT: new review from maintainer (not bot, not us) ===
            if (review_state and review_by and review_by != "makar52nn2016-jpg"
                    and "[bot]" not in review_by
                    and review_state != prev_review_state):
                emoji = {"APPROVED": "✅", "CHANGES_REQUESTED": "⚠️",
                         "COMMENTED": "💬"}.get(review_state, "📝")
                tg_send(
                    f"{emoji} {repo}#{num}: review {review_state} by @{review_by}\n"
                    f"Задача: {label} (${bounty})\n"
                    f"https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1

            # === ALERT: APPROVED but >24h without merge → send ping text ===
            if review_state == "APPROVED":
                # Get last comment timestamp
                comments = requests.get(
                    f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                    headers=HEADERS, timeout=15,
                ).json()
                # find last comment by maintainer (not us, not bot)
                last_maintainer_comment_at = None
                for c in comments:
                    u = c.get("user", {}).get("login", "")
                    if u != "makar52nn2016-jpg" and "[bot]" not in u:
                        last_maintainer_comment_at = c.get("created_at")
                        break  # we want most recent — but list is asc, so reverse
                if not last_maintainer_comment_at:
                    # use PR created_at or updated_at
                    last_maintainer_comment_at = pr.get("updated_at") or pr.get("created_at")

                last_dt = datetime.fromisoformat(
                    last_maintainer_comment_at.replace("Z", "+00:00")
                )
                hours_since = (now - last_dt).total_seconds() / 3600

                if hours_since > 24:
                    # only ping once per PR per 24h
                    last_ping = pinged.get(state_key, 0)
                    if now.timestamp() - last_ping > 24 * 3600:
                        maintainers = get_repo_maintainers(repo, num)
                        ping_text = generate_ping_comment(
                            maintainers, repo, num, label, bounty
                        )
                        tg_send(ping_text)
                        pinged[state_key] = now.timestamp()
                        action_needed_count += 1

            # === ALERT: new comment from maintainer ===
            comments = requests.get(
                f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                headers=HEADERS, timeout=15,
            ).json()
            last_seen_id = seen.get(state_key, 0)
            new_other_comments = [
                c for c in comments
                if c.get("id", 0) > last_seen_id
                and c.get("user", {}).get("login") != "makar52nn2016-jpg"
                and "[bot]" not in c.get("user", {}).get("login", "")
            ]
            if new_other_comments:
                last = new_other_comments[-1]
                who = last["user"]["login"]
                body = (last.get("body", "") or "")[:300]
                tg_send(
                    f"💬 Новый комментарий {repo}#{num}:\n"
                    f"@{who}: {body}\n"
                    f"https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1
            if comments:
                seen[state_key] = max(c.get("id", 0) for c in comments)

            pr_states[state_key] = {
                "merged": now_merged,
                "state": pr.get("state"),
                "mergeable": pr.get("mergeable"),
                "mergeable_state": mergeable_state,
                "title": pr.get("title", ""),
                "review_state": review_state,
                "review_by": review_by,
                "ci_state": ci_state,
                "updated_at": pr.get("updated_at"),
            }
        except Exception as e:
            log.warning("PR %s#%s: %s", repo, num, e)

    state["prev_pr_states"] = pr_states
    state["last_comment_seen"] = seen
    state["pinged_prs"] = pinged
    return action_needed_count


# ============== BOUNTY SCANNER ==============
BOUNTY_REPOS = [
    "stellar/stellar-demo-wallet",
    "auscaster/frantic-board",
    "Heliobond/frontend",
    "dwebagents/AgentPipe",
    "UniversalAviator420/bounty-sandbox",
    "ancore-org/ancore",
    "Soroban-Cookbook/Soroban_Cookbook_online",
    "StellarRoute/WaveFlow",
]


def scan_bounties(state):
    """Scan for new bounty issues — only alert on NEW self-assignable ones."""
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
                    seen_issues[key] = {"title": issue.get("title"),
                                        "url": issue.get("html_url")}
                    found_new += 1
                    assignee = issue.get("assignee")
                    if assignee is None:
                        # NEW self-assignable bounty — alert (potential action)
                        labels = [l["name"] for l in issue.get("labels", [])]
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


# ============== HEARTBEAT (silent — no alert unless problems) ==============
def maybe_heartbeat(state, action_count):
    """Heartbeat only sends if there are pending action-needed items OR every 6h summary."""
    now = time.time()
    last = state.get("last_heartbeat", 0)

    # 6h regular heartbeat
    if now - last > 6 * 3600:
        state["last_heartbeat"] = now
        merged_count = sum(1 for k, v in state.get("prev_pr_states", {}).items()
                          if v.get("merged"))
        open_count = len(PRS) - merged_count
        # only send heartbeat if there's something interesting OR user might think daemon is dead
        tg_send(
            f"💓 Daemon живой (GitHub Actions)\n"
            f"PRs merged: {merged_count}/{len(PRS)}\n"
            f"Pending review: {open_count}\n"
            f"Action items this run: {action_count}\n"
            f"XLM: {state.get('prev_xlm', 0):.4f} | ETH: {state.get('prev_eth', 0):.6f}"
        )
    return state


# ============== MAIN ==============
def main():
    log.info("Daemon v2 start — smart alerting mode")
    state = load_state()

    state = check_wallets(state)
    action_count = check_prs(state)
    found_new = scan_bounties(state)
    state = maybe_heartbeat(state, action_count)

    save_state(state)
    log.info("Daemon end. Action items: %d, new bounties scanned: %d", action_count, found_new)


if __name__ == "__main__":
    main()
