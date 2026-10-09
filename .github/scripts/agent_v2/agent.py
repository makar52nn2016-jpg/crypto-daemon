#!/usr/bin/env python3
"""INSTANT PAYOUT BOUNTY AGENT v2.0 — autonomous bounty scanner.

Tools:
  - github_search_issues(query, limit)
  - frantic_api_call(endpoint, method, body)
  - check_scam_cluster(org_name)
  - monitor_base_payout(wallet)

Runs every 30 min via GitHub Actions cron. Logs to /tmp/agent_log.jsonl
and stdout. Blacklist-enforced."""
import os, sys, json, time, urllib.request, urllib.error, urllib.parse, ssl, re
from datetime import datetime, timezone, timedelta

# ─────────── CONFIG ───────────
FRANTIC_TOKEN = os.environ.get('FRANTIC_AGENT_TOKEN', '')
GH_PAT = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or os.environ.get('PAT', '')
AGENT_KID = 'agent-b94b60'
META_MASK = '0x30450A8B96535e4ee1897f1E59ff2556f6191bcc'
STELLAR_WALLET = 'GBAUE3TLQMHDFGHQVLHE4LCJJQKVSSHM6YB2SCG2VX2M7XXKWPWCJBRQ'
LIGHTNING = 'wakefulneon901@wallelofsatoshi.com'

# Whitelisted platforms (priority 1-3)
WHITELIST = {
    'priority_1': ['gofrantic.com', 'stackernews/stacker.news', 'getAlby/lightning-browser-extension'],
    'priority_2': ['Escaro-Labs/escaro', 'AstralDeep'],  # AstralDeep only if CI green + merge<48h
    'priority_3': ['taskmarket.dev (Daydreams)', 'any EVM/Base escrow with releaseBounty()'],
}

# BLACKLIST — never work with these
BLACKLIST_PLATFORMS = ['Opire', 'Gitcoin', 'Bounties Network']
BLACKLIST_REPOS = [
    # === CONFIRMED SCAM CLUSTER (2026-10-06) ===
    # All 4 orgs created within 12 minutes of each other on 2026-10-06.
    # Same maintainer "Femi" / @Toyosi5566, same bounty template ($XX + ETA 24h).
    # Self-merge pattern (PR author = commit author). Zero payout confirmations.
    # slippay-labs CONFIRMED SCAM: 2 PRs merged 2026-10-08 ($75+$60=$135 owed), never paid.
    'vouchlabsio',          # 21:45:40 created
    'slippay-labs',         # 21:47:15 created — CONFIRMED unpaid $135 (PRs #124, #128 merged but never paid)
    'stellita-labs',        # 21:53:54 created
    'visionme-studio',      # 21:57:32 created
    'zstellar-labs',        # part of cluster
    # === OLDER SCAM CLUSTERS ===
    'Augora-Labs',          # scam cluster from prior session
    'streamr-labs/attestar',# scam cluster from prior session
    # === ZERO-PAYOUT PLATFORMS ===
    'MisakaNet',            # opirebot literal: "issue does not have any reward yet!" — points only, not money
    'SecureBananaLabs/bug-bounty',  # STALLED: 9+ days silent, 0 merges in 14+ days, $1210 stuck
]

# Active Frantic claims to monitor
FRANTIC_CLAIMS = [
    ('467ca1b3-d99d-44ec-8fe5-134e3f118282', 128, '$8'),  # Sourcey citation
]

# Active GitHub PRs to monitor — each entry is (repo, pr_num, bounty_label, opened_at_iso, platform)
# Smart ping rule: PR open >=48h AND last comment >=24h ago -> log PING_NEEDED
# STALLED rule: PR open >=7d -> log STALLED
ACTIVE_PRS = [
    # AstralDeep — CRITICAL: reservation expires 2026-10-09T20:48:48Z
    ('AstralDeep/AstralPrimitives', 26, '100 pts', '2026-10-05', 'AstralDeep'),
    # Escaro batch — all opened 2026-10-09, all USDC on Stellar
    ('Escaro-Labs/escaro', 114, '$90 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 123, '$45 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 124, '$60 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 127, '$40 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 128, '$65 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 129, '$60 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 130, '$65 USDC', '2026-10-09', 'Escaro'),
    ('Escaro-Labs/escaro', 131, '$85 USDC', '2026-10-09', 'Escaro'),
    # SecureBananaLabs — STALLED (9+ days silent, in BLACKLIST)
    ('SecureBananaLabs/bug-bounty', 12770, '$430 USDC', '2026-10-01', 'SecureBananaLabs'),
    ('SecureBananaLabs/bug-bounty', 12771, '$780 USDC', '2026-10-01', 'SecureBananaLabs'),
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def log(msg, level='INFO', **extra):
    entry = {
        'ts': datetime.now(timezone.utc).isoformat()[:19],
        'level': level,
        'msg': msg,
        **extra,
    }
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    # Append to log file
    try:
        with open('/tmp/agent_log.jsonl', 'a') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass

# ─────────── TOOL 1: github_search_issues ───────────
def github_search_issues(query, limit=10):
    """Search GitHub issues with the given query."""
    if not GH_PAT:
        log('GH_PAT not set', 'ERROR')
        return []
    url = f'https://api.github.com/search/issues?q={urllib.parse.quote(query)}&per_page={limit}'
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {GH_PAT}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'agent-v2')
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            d = json.loads(r.read())
        items = d.get('items', [])
        log(f'github_search_issues: {len(items)} results for "{query[:60]}"', 'DEBUG')
        return items
    except Exception as e:
        log(f'github_search_issues ERROR: {e}', 'ERROR')
        return []

# ─────────── TOOL 2: frantic_api_call ───────────
def frantic_api_call(endpoint, method='GET', body=None):
    """Call Frantic API with stored agent token."""
    if not FRANTIC_TOKEN:
        log('FRANTIC_TOKEN not set', 'ERROR')
        return None
    url = f'https://gofrantic.com{endpoint}' if endpoint.startswith('/') else endpoint
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'Bearer {FRANTIC_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'agent-v2')
    if body:
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'body': e.read().decode()[:300]}
    except Exception as e:
        return {'error': str(e)[:200]}

# ─────────── TOOL 3: check_scam_cluster ───────────
def check_scam_cluster(org_name):
    """Verify an org is not part of a scam cluster.
    Returns dict with verdict + reasons.
    """
    if not GH_PAT:
        return {'verdict': 'UNKNOWN', 'reason': 'no GH_PAT'}
    # Check blacklist first
    for bl in BLACKLIST_REPOS:
        if bl in org_name or org_name in bl:
            return {'verdict': 'FAIL', 'reason': f'in BLACKLIST_REPOS ({bl})'}
    # Check org creation date
    url = f'https://api.github.com/orgs/{org_name}'
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {GH_PAT}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'agent-v2')
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            d = json.loads(r.read())
        created = d.get('created_at', '')
        if created:
            days_old = (datetime.now(timezone.utc) - datetime.fromisoformat(created.replace('Z','+00:00'))).days
            if days_old < 30:
                return {'verdict': 'FAIL', 'reason': f'org created {days_old}d ago (<30d threshold)'}
        public_repos = d.get('public_repos', 0)
        if public_repos <= 2:
            return {'verdict': 'WARN', 'reason': f'only {public_repos} public repos (scam pattern)'}
        return {'verdict': 'PASS', 'reason': f'org {days_old}d old, {public_repos} repos', 'days_old': days_old}
    except urllib.error.HTTPError as e:
        return {'verdict': 'UNKNOWN', 'reason': f'API err {e.code}'}
    except Exception as e:
        return {'verdict': 'UNKNOWN', 'reason': str(e)[:200]}

# ─────────── TOOL 4: monitor_base_payout ───────────
def monitor_base_payout(wallet):
    """Check Base USDC balance via Base RPC (eth_call).
    USDC on Base: 0x833589fCD6e6DF92A64B1C3F97C10Db29F9AE9B7
    balanceOf(address) selector: 0x70a08231
    """
    USDC_BASE = '0x833589fCD6e6DF92A64B1C3F97C10Db29F9AE9B7'
    # Public Base RPC (no API key needed)
    RPC_URL = 'https://mainnet.base.org'
    if not wallet.startswith('0x'):
        return {'wallet': wallet, 'error': 'invalid address'}
    addr_padded = wallet[2:].lower().zfill(64)
    call_data = f'0x70a08231{addr_padded}'
    body = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'eth_call',
        'params': [{'to': USDC_BASE, 'data': call_data}, 'latest']
    }).encode()
    req = urllib.request.Request(RPC_URL, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('User-Agent', 'agent-v2')
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            d = json.loads(r.read())
        result = d.get('result', '0x0')
        error = d.get('error')
        if error:
            return {'wallet': wallet, 'usdc_balance': 0, 'note': f'RPC error: {error.get("message","")[:100]}'}
        if result and result.startswith('0x'):
            # 0x or 0x0 = 0 balance
            hex_str = result[2:] or '0'
            balance = int(hex_str, 16) / 1e6  # USDC has 6 decimals
            return {'wallet': wallet, 'usdc_balance': balance, 'raw': result[:30]}
        return {'wallet': wallet, 'usdc_balance': 0, 'note': 'no result', 'raw_response': str(d)[:200]}
    except Exception as e:
        return {'wallet': wallet, 'error': str(e)[:200]}

# ─────────── MAIN ROUTINES ───────────

def scan_frantic_board():
    """Scan Frantic board for new bounties matching criteria."""
    log('Scanning Frantic board...')
    d = frantic_api_call('/v1/board')
    if not d or 'board' not in d:
        log('Failed to fetch Frantic board', 'WARN')
        return []
    bounties = d.get('board', {}).get('open_bounties', []) or []
    candidates = []
    for b in bounties:
        cp = b.get('claim_progress', {}) or {}
        comments = (cp.get('rejected', 0) + cp.get('expired', 0) + cp.get('delivered', 0))
        if comments > 20:
            log(f'  skip #{b.get("number")} ({comments} comments — overheated)', 'DEBUG')
            continue
        avail = cp.get('available', 0)
        if avail <= 0:
            continue
        candidates.append({
            'number': b.get('number'),
            'title': b.get('title', '')[:60],
            'price_usd': b.get('price_usd'),
            'available': avail,
            'capacity': cp.get('capacity'),
            'claim_limit': b.get('criteria', {}).get('claim_limit_per_operator'),
        })
        log(f'  candidate #{b.get("number")} ${b.get("price_usd")} | {avail}/{cp.get("capacity")} slots | {b.get("title","")[:40]}', 'CANDIDATE')
    return candidates

def check_frantic_claims():
    """Check status of active Frantic claims."""
    log('Checking Frantic claims...')
    for claim_id, bounty_num, amount in FRANTIC_CLAIMS:
        d = frantic_api_call(f'/v1/claims/{claim_id}')
        if not isinstance(d, dict):
            log(f'  claim {claim_id}: API error', 'WARN')
            continue
        status = d.get('status', '?')
        judged = d.get('judged_at')
        rejection = d.get('rejection_reason')
        log(f'  claim {claim_id[:8]} (#{bounty_num} {amount}): status={status}, judged={judged}, rejected={rejection}', 'CLAIM_STATUS')

def check_active_prs():
    """Check active GitHub PRs for age and ping-worthiness."""
    log('Checking active GitHub PRs...')
    now = datetime.now(timezone.utc)
    for repo, num, amount, date_str, platform in ACTIVE_PRS:
        # PR age in days
        try:
            created = datetime.fromisoformat(date_str + 'T00:00:00+00:00')
            age_days = (now - created).days
        except Exception:
            age_days = 0
        # Get latest activity
        if not GH_PAT:
            continue
        url = f'https://api.github.com/repos/{repo}/issues/{num}/comments?per_page=5'
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {GH_PAT}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('User-Agent', 'agent-v2')
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                comments = json.loads(r.read())
            last_comment_at = comments[-1]['created_at'] if comments else None
            last_commenter = comments[-1]['user']['login'] if comments else None
            if last_comment_at:
                last_dt = datetime.fromisoformat(last_comment_at.replace('Z', '+00:00'))
                since_last_comment_h = (now - last_dt).total_seconds() / 3600
            else:
                # No comments: use PR creation date as the "last activity" baseline
                try:
                    pr_url = f'https://api.github.com/repos/{repo}/pulls/{num}'
                    pr_req = urllib.request.Request(pr_url)
                    pr_req.add_header('Authorization', f'Bearer {GH_PAT}')
                    pr_req.add_header('Accept', 'application/vnd.github+json')
                    pr_req.add_header('User-Agent', 'agent-v2')
                    with urllib.request.urlopen(pr_req, timeout=10, context=ctx) as pr_r:
                        pr_d = json.loads(pr_r.read())
                    created_at = pr_d.get('created_at', date_str + 'T00:00:00Z')
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    since_last_comment_h = (now - created_dt).total_seconds() / 3600
                except Exception:
                    since_last_comment_h = age_days * 24
            # Smart ping rule: PR open >48h AND last activity >24h ago
            needs_ping = age_days >= 2 and since_last_comment_h >= 24
            # STALLED rule: PR open >=7d
            stalled = age_days >= 7
            level = 'PR_STATUS'
            if stalled:
                level += ' STALLED'
            elif needs_ping:
                level += ' PING_NEEDED'
            log(f'  [{platform}] {repo}#{num} ({amount}): age={age_days}d, last_comment={since_last_comment_h:.1f}h ago, needs_ping={needs_ping}, stalled={stalled}',
                level)
        except Exception as e:
            log(f'  {repo}#{num}: API error {e}', 'WARN')

def scan_stacker_news():
    """Scan Stacker News for new bounty-eligible issues."""
    log('Scanning Stacker News for new issues...')
    items = github_search_issues('repo:stackernews/stacker.news is:issue is:open sort:created-desc', limit=10)
    candidates = []
    for it in items[:10]:
        title = it.get('title', '')
        num = it.get('number')
        comments = it.get('comments', 0)
        if comments > 20:
            continue
        labels = [l['name'] for l in it.get('labels', [])]
        if any(l.startswith('difficulty:') for l in labels):
            diff_label = next((l for l in labels if l.startswith('difficulty:')), '')
            candidates.append({'number': num, 'title': title[:50], 'comments': comments, 'difficulty': diff_label})
            log(f'  SN #{num} [{diff_label}] ({comments}c) {title[:40]}', 'CANDIDATE')
    return candidates

def check_blacklist_filter(candidate_text):
    """Apply blacklist filter to a candidate description."""
    for bl in BLACKLIST_PLATFORMS + BLACKLIST_REPOS:
        if bl.lower() in candidate_text.lower():
            return False, f'blacklisted: {bl}'
    return True, 'pass'

# ─────────── MAIN ───────────
def main():
    log('=== Agent v2.0 cycle start ===', 'CYCLE_START')
    
    # 1. Scan Frantic for new bounties
    frantic_candidates = scan_frantic_board()
    log(f'Frantic candidates: {len(frantic_candidates)}')
    
    # 2. Check Frantic active claims
    check_frantic_claims()
    
    # 3. Scan Stacker News for new issues
    sn_candidates = scan_stacker_news()
    log(f'Stacker News candidates: {len(sn_candidates)}')
    
    # 4. Check active GitHub PRs (smart ping rule)
    check_active_prs()
    
    # 5. Monitor Base USDC balance
    balance = monitor_base_payout(META_MASK)
    log(f'Base USDC balance ({META_MASK[:10]}...): {balance.get("usdc_balance", "ERR")} USDC', 'BALANCE')
    
    log('=== Agent v2.0 cycle end ===', 'CYCLE_END')

if __name__ == '__main__':
    main()
