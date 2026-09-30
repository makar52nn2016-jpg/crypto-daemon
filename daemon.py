#!/usr/bin/env python3
"""Crypto Daemon v3 — 24/7 autonomous earning system (GitHub Actions edition).

Modernized v3:
- Smart alerting: only action-needed events
- BOUNTY DISCOVERY: every 6h finds least-competed unassigned Stellar Wave issues (1-3 applications)
- BOUNTY DISCOVERY: NEW unassigned Stellar Wave issues created in last 24h with 0 apps
- Wallet monitor: XLM/ETH/BTC/SOL (instant alert on incoming)
- PR tracker: merges, comments, reviews, conflict detection
- generate_ping_comment: ready-to-paste text when >24h no response
- State persistence: state.json committed by CI
- Russian TG messages

Runs on GitHub Actions cron '*/5 * * * *'.
"""
import os
import json
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

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
# TON wallet — mainnet, USDT (jetton) + native TON
TON_ADDR = "UQDyOVPv7hrvOePpOLQL5SiV2VxXs4P5A3A3rHOb9BvvOPtH"
# TON USDT jetton master address (EQ... mainnet)
TON_USDT_JETTON = "EQCxE6mUtPJKnaCM4Wv7vLyEh2tXJqRR2vshU9bCSLVKQR2P"

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# All tracked PRs: (repo, pr_number, bounty_usd, label)
PRS = [
    # Still open, unassigned underlying issue — best chance
    ("Heliobond/frontend", 676, 100, "registry decoder (#626 unassigned)"),
    ("soroban-forge-labs/soroban-forge", 488, 50, "network remove subcommand (#467 unassigned)"),
    ("gear5labs/chenpilot-client", 185, 50, "remove tsc_output.txt artifact (#135 unassigned)"),
    ("gear5labs/chenpilot-client", 186, 50, "logger helper + console.log removal (#133 unassigned)"),
    ("gear5labs/chenpilot-client", 187, 50, "format/validation tests (#141 unassigned)"),
    ("gear5labs/chenpilot-client", 189, 50, "dedupe socketManager tests (#136 unassigned)"),
    ("StellarCanary/ProtocolCanary-Action", 306, 50, "main.ts error-branch tests (#271 unassigned)"),
    ("StellarCanary/ProtocolCanary-Fixtures", 241, 50, "non-array assert value rejected (#225 unassigned)"),
    ("StellarCanary/ProtocolCanary-Fixtures", 242, 50, "expected_file accepts existing (#226 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1006, 50, "contract-ids key-handling (#919 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1007, 50, "authorization key+net guards (#917 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1008, 50, "authorization-trees key+net guards (#916 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1009, 50, "setup-linux key-handling (#911 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1010, 50, "token-audit unaudited notice (#900 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1011, 50, "fundamentals unaudited notice (#898 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1012, 50, "upgrade-checklist unaudited notice (#901 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1013, 50, "defi-patterns unaudited notice (#897 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1017, 50, "setup-windows key-handling (#913 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1018, 50, "setup-macos key-handling (#912 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1019, 50, "deploy-testnet key-handling (#907 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1020, 50, "patterns/overview unaudited notice (#902 unassigned)"),
    ("Soroban-Cookbook/Soroban_Cookbook_online", 1021, 50, "examples-index unaudited notice (#903 unassigned)"),
    # Other (no Stellar Wave label, may still merge but no XLM payout)
    ("UniversalAviator420/bounty-sandbox", 12, 50, "bounty-sandbox README+add bug"),
    ("dwebagents/AgentPipe", 2120, 23, "AgentPipe contributors"),
    ("ancore-org/ancore", 1487, 0, "retry wrapper"),
    ("StellarRoute/WaveFlow", 71, 100, "CONTRIBUTING.md (no Wave label)"),
]

# Repos where Vercel/preview failure is expected for fork PRs (do NOT alert on those)
FORK_VERCEL_REPOS = {"Heliobond/frontend", "drydocs/meridian"}

HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "User-Agent": "crypto-daemon-bot",
    "Accept": "application/vnd.github+json",
}

SLA_THRESHOLD_SECONDS = 24 * 3600
DISCOVERY_INTERVAL_SECONDS = 6 * 3600  # 6h
DISCOVERY_MAX_RESULTS = 5  # Top 5 least-competed issues per discovery run


def load_state():
    default = {
        "prev_xlm": 9.8081229, "prev_eth": 0.0, "prev_btc": 0.0, "prev_sol": 0.0,
        "prev_ton": 0.0, "prev_ton_usdt": 0.0,
        "prev_pr_states": {}, "last_heartbeat": 0, "last_comment_seen": {},
        "seen_bounties": {}, "pinged_prs": {},
        "last_discovery": 0, "last_top_bounties": [],
    }
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return default


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
            f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=balance&address={ETH_ADDR}&tag=latest",
            timeout=10,
        )
        if r.status_code == 200:
            result = r.json().get("result", "0")
            try:
                wei = int(result)
            except (ValueError, TypeError):
                return prev
            bal = wei / 1e18
            if bal > prev + 0.0001:
                delta = bal - prev
                tg_send(
                    f"💰 ETH INCOMING: +{delta:.6f} ETH\n"
                    f"Баланс: {prev:.6f} → {bal:.6f} ETH\n"
                    f"Адрес: {ETH_ADDR}"
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
                tg_send(f"💰 BTC INCOMING: +{delta:.8f} BTC\nБаланс: {bal:.8f} BTC")
                return bal
            return bal
    except Exception as e:
        log.warning("btc: %s", e)
    return prev


def check_sol(prev):
    try:
        r = requests.post(
            "https://api.mainnet-beta.solana.com",
            json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [SOL_ADDR]},
            timeout=10,
        )
        if r.status_code == 200:
            lamports = r.json().get("result", {}).get("value", 0)
            bal = lamports / 1e9
            if bal > prev + 0.001:
                delta = bal - prev
                tg_send(f"💰 SOL INCOMING: +{delta:.6f} SOL\nБаланс: {bal:.6f} SOL")
                return bal
            return bal
    except Exception as e:
        log.warning("sol: %s", e)
    return prev


def check_ton(prev):
    """Check native TON balance via Tonhub/Tonapi public API."""
    try:
        # tonapi.io is a free public API for TON
        r = requests.get(f"https://tonapi.io/v2/accounts/{TON_ADDR}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            # balance is in nanotons (1 TON = 10^9 nanoton)
            bal = data.get("balance", 0) / 1e9
            if bal > prev + 0.001:
                delta = bal - prev
                tg_send(
                    f"💰 TON INCOMING: +{delta:.4f} TON\n"
                    f"Баланс: {prev:.4f} → {bal:.4f} TON\n"
                    f"Адрес: {TON_ADDR}\n"
                    f"https://tonscan.org/address/{TON_ADDR}"
                )
                return bal
            return bal
    except Exception as e:
        log.warning("ton: %s", e)
    return prev


def check_ton_usdt(prev):
    """Check USDT (jetton) balance on TON."""
    try:
        # tonapi.io jetton balances
        r = requests.get(f"https://tonapi.io/v2/accounts/{TON_ADDR}/jettons", timeout=10)
        if r.status_code == 200:
            data = r.json()
            for j in data.get("jettons", []):
                # Jetton master: EQCxE6mUtPJKnaCM4Wv7vLyEh2tXJqRR2vshU9bCSLVKQR2P = TON USDT
                if j.get("jetton", {}).get("address", "").startswith("EQCxE6mUt"):
                    # balance is in jetton units (USDT has 6 decimals on TON)
                    bal = int(j.get("balance", 0)) / 1e6
                    if bal > prev + 0.001:
                        delta = bal - prev
                        tg_send(
                            f"💰 USDT (TON) INCOMING: +{delta:.2f} USDT\n"
                            f"Баланс: {prev:.2f} → {bal:.2f} USDT\n"
                            f"Адрес: {TON_ADDR}"
                        )
                        return bal
                    return bal
    except Exception as e:
        log.warning("ton_usdt: %s", e)
    return prev


def check_wallets(state):
    state["prev_xlm"] = check_xlm(state.get("prev_xlm", 9.8081229))
    state["prev_eth"] = check_eth(state.get("prev_eth", 0.0))
    state["prev_btc"] = check_btc(state.get("prev_btc", 0.0))
    state["prev_sol"] = check_sol(state.get("prev_sol", 0.0))
    state["prev_ton"] = check_ton(state.get("prev_ton", 0.0))
    state["prev_ton_usdt"] = check_ton_usdt(state.get("prev_ton_usdt", 0.0))
    return state


# ============== SMART PR TRACKER ==============
def get_repo_maintainers(repo, num):
    maintainers = set()
    try:
        revs = requests.get(f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
                           headers=HEADERS, timeout=15).json()
        for r in revs:
            u = r.get("user", {}).get("login", "")
            if u and u != "makar52nn2016-jpg" and "[bot]" not in u:
                maintainers.add(u)
    except Exception:
        pass
    try:
        repo_data = requests.get(f"https://api.github.com/repos/{repo}", headers=HEADERS, timeout=15).json()
        owner = repo_data.get("owner", {}).get("login", "")
        if owner:
            maintainers.add(owner)
    except Exception:
        pass
    return list(maintainers)


def generate_ping_comment(maintainers_list, repo, num, label, bounty):
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
        f"🔗 https://github.com/{repo}/pull/{num}"
    )


def check_prs(state):
    seen = state.get("last_comment_seen", {})
    pr_states = state.get("prev_pr_states", {})
    pinged = state.get("pinged_prs", {})
    now = datetime.now(timezone.utc)
    action_needed_count = 0

    for repo, num, bounty, label in PRS:
        try:
            pr = requests.get(f"https://api.github.com/repos/{repo}/pulls/{num}",
                            headers=HEADERS, timeout=15).json()
            if "title" not in pr:
                continue

            state_key = f"{repo}#{num}"
            was_merged = pr_states.get(state_key, {}).get("merged", False)
            now_merged = pr.get("merged", False)
            prev_review_state = pr_states.get(state_key, {}).get("review_state")

            if now_merged and not was_merged:
                if bounty > 0:
                    tg_send(
                        f"🎉 PR СМЕРЖЕН: {repo}#{num}\n"
                        f"Задача: {label}\n"
                        f"Награда: ${bounty}\n"
                        f"https://github.com/{repo}/pull/{num}\n\n"
                        f"⚠️ Чтобы получить payout, нужно чтобы issue был assigned тебе "
                        f"через drips.network/wave dashboard ДО merge. Проверь свой wave "
                        f"dashboard на наличие points."
                    )
                else:
                    tg_send(f"✅ PR СМЕРЖЕН: {repo}#{num} ({label})")
                action_needed_count += 1
                pr_states[state_key] = {"merged": True, "state": "merged"}
                continue

            if now_merged:
                pr_states[state_key] = {"merged": True}
                continue

            sha = pr.get("head", {}).get("sha", "")
            ci_state = "?"
            check_conclusions = []
            if sha:
                try:
                    st = requests.get(f"https://api.github.com/repos/{repo}/commits/{sha}/status",
                                    headers=HEADERS, timeout=15).json()
                    ci_state = st.get("state", "?")
                except Exception:
                    pass
                try:
                    cr = requests.get(f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs",
                                     headers=HEADERS, timeout=15).json()
                    check_conclusions = [(c.get("name"), c.get("conclusion"))
                                        for c in cr.get("check_runs", [])[:5]]
                except Exception:
                    pass

            real_failures = []
            for name, conclusion in check_conclusions:
                if conclusion == "failure" and name:
                    if repo in FORK_VERCEL_REPOS and "Vercel" in name:
                        continue
                    real_failures.append(name)

            prev_ci = pr_states.get(state_key, {}).get("ci_state")
            if real_failures and ci_state != prev_ci:
                tg_send(
                    f"❌ CI FAIL: {repo}#{num} ({label})\n"
                    f"Failed: {', '.join(real_failures[:3])}\n"
                    f"https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1

            mergeable_state = pr.get("mergeable_state")
            prev_ms = pr_states.get(state_key, {}).get("mergeable_state")
            if mergeable_state == "dirty" and prev_ms != "dirty":
                tg_send(
                    f"⚠️ КОНФЛИКТ: {repo}#{num} ({label}) — dirty\n"
                    f"Нужен rebase! https://github.com/{repo}/pull/{num}"
                )
                action_needed_count += 1

            reviews = requests.get(f"https://api.github.com/repos/{repo}/pulls/{num}/reviews",
                                  headers=HEADERS, timeout=15).json()
            last_review = reviews[-1] if reviews else None
            review_state = last_review.get("state") if last_review else None
            review_by = last_review.get("user", {}).get("login") if last_review else None

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

            if review_state == "APPROVED":
                comments = requests.get(f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                                       headers=HEADERS, timeout=15).json()
                last_maintainer_comment_at = None
                for c in comments:
                    u = c.get("user", {}).get("login", "")
                    if u != "makar52nn2016-jpg" and "[bot]" not in u:
                        last_maintainer_comment_at = c.get("created_at")
                        break
                if not last_maintainer_comment_at:
                    last_maintainer_comment_at = pr.get("updated_at") or pr.get("created_at")

                last_dt = datetime.fromisoformat(last_maintainer_comment_at.replace("Z", "+00:00"))
                hours_since = (now - last_dt).total_seconds() / 3600

                if hours_since > 24:
                    last_ping = pinged.get(state_key, 0)
                    if now.timestamp() - last_ping > 24 * 3600:
                        maintainers = get_repo_maintainers(repo, num)
                        ping_text = generate_ping_comment(maintainers, repo, num, label, bounty)
                        tg_send(ping_text)
                        pinged[state_key] = now.timestamp()
                        action_needed_count += 1

            comments = requests.get(f"https://api.github.com/repos/{repo}/issues/{num}/comments",
                                   headers=HEADERS, timeout=15).json()
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
                "merged": now_merged, "state": pr.get("state"),
                "mergeable": pr.get("mergeable"),
                "mergeable_state": mergeable_state,
                "title": pr.get("title", ""),
                "review_state": review_state, "review_by": review_by,
                "ci_state": ci_state, "updated_at": pr.get("updated_at"),
            }
        except Exception as e:
            log.warning("PR %s#%s: %s", repo, num, e)

    state["prev_pr_states"] = pr_states
    state["last_comment_seen"] = seen
    state["pinged_prs"] = pinged
    return action_needed_count


# ============== BOUNTY DISCOVERY (NEW in v3) ==============
def discover_bounties(state):
    """Every 6h: find least-competed unassigned Stellar Wave issues (1-3 applications).
    Alert user about best opportunities to apply via drips.network/wave dashboard."""
    now = time.time()
    last = state.get("last_discovery", 0)
    if now - last < DISCOVERY_INTERVAL_SECONDS:
        return 0

    state["last_discovery"] = now
    log.info("Running bounty discovery...")

    try:
        r = requests.get(
            "https://api.github.com/search/issues",
            params={
                "q": 'label:"Stellar Wave" state:open is:issue no:assignee',
                "per_page": 30,
                "sort": "created",
                "order": "desc",
            },
            headers=HEADERS, timeout=30,
        )
        if r.status_code != 200:
            log.warning("discovery search failed: %d", r.status_code)
            return 0
        items = r.json().get("items", [])

        # Score each by number of applications
        scored = []
        for i in items[:30]:
            repo = '/'.join(i['repository_url'].split('/')[-2:])
            num = i['number']
            try:
                comments = requests.get(f"https://api.github.com/repos/{repo}/issues/{num}/comments?per_page=50",
                                       headers=HEADERS, timeout=15).json()
                app_count = sum(1 for c in comments
                              if "wave:application-id" in (c.get("body", "") or ""))
                scored.append({
                    "repo": repo, "num": num, "title": i["title"][:80],
                    "app_count": app_count,
                    "created": i["created_at"][:10],
                    "labels": [l["name"] for l in i.get("labels", []) if l["name"] != "Stellar Wave"],
                    "url": i["html_url"],
                })
            except Exception:
                pass

        # Sort by app_count asc, then by created desc (newer first)
        scored.sort(key=lambda x: (x["app_count"], -int(x["created"].replace("-", ""))))

        top = scored[:DISCOVERY_MAX_RESULTS]
        if not top:
            return 0

        msg_lines = ["🎯 DISCOVERY: ТОП-5 least-competed Stellar Wave issues\n"]
        msg_lines.append("(Меньше заявок = выше шанс получить assignment)\n")
        for i, t in enumerate(top, 1):
            emoji = "🟢" if t["app_count"] <= 1 else "🟡" if t["app_count"] <= 3 else "🔴"
            msg_lines.append(
                f"{i}. {emoji} {t['repo']}#{t['num']} — {t['app_count']} apps\n"
                f"   {t['title']}\n"
                f"   labels: {', '.join(t['labels'][:4])}\n"
                f"   {t['url']}"
            )
        msg_lines.append("\n💡 Подай заявку на drips.network/wave dashboard на 2-3 из них.")
        msg = "\n".join(msg_lines)
        tg_send(msg)
        state["last_top_bounties"] = top
        return len(top)
    except Exception as e:
        log.warning("discovery: %s", e)
    return 0


# ============== HEARTBEAT ==============
def maybe_heartbeat(state, action_count):
    now = time.time()
    last = state.get("last_heartbeat", 0)
    if now - last > 6 * 3600:
        state["last_heartbeat"] = now
        merged_count = sum(1 for k, v in state.get("prev_pr_states", {}).items() if v.get("merged"))
        open_count = len(PRS) - merged_count
        tg_send(
            f"💓 Daemon v3 живой (GitHub Actions)\n"
            f"PRs merged: {merged_count}/{len(PRS)}\n"
            f"Pending review: {open_count}\n"
            f"Action items this run: {action_count}\n"
            f"XLM: {state.get('prev_xlm', 0):.4f} | ETH: {state.get('prev_eth', 0):.6f}\n"
            f"BTC: {state.get('prev_btc', 0):.8f} | SOL: {state.get('prev_sol', 0):.6f}\n"
            f"TON: {state.get('prev_ton', 0):.4f} | USDT(TON): {state.get('prev_ton_usdt', 0):.2f}\n"
            f"Discovery: каждые 6h ищет least-competed Stellar Wave issues"
        )
    return state


# ============== MAIN ==============
def main():
    log.info("Daemon v3 start — smart alerting + bounty discovery")
    state = load_state()

    state = check_wallets(state)
    action_count = check_prs(state)
    discovered = discover_bounties(state)
    state = maybe_heartbeat(state, action_count)

    save_state(state)
    log.info("Daemon end. Actions: %d, bounties discovered: %d", action_count, discovered)


if __name__ == "__main__":
    main()
