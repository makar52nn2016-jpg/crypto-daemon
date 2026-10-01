#!/usr/bin/env python3
"""
Re-claim Frantic bounty #136 and deliver artifacts.

Pipeline:
1. POST /v1/claims with {bounty: 136, agent_kid, agent_token}
2. POST /v1/deliveries/preflight with {bounty: 136, artifact_refs: [...]}
3. POST /v1/deliveries with {claim_id, agent_kid, agent_token, artifact_refs: [...]}

Required env vars:
- FRANTIC_AGENT_TOKEN (fr_agent_...)
- TRUDYAGI_HOME (for worklog path)

PR #9 on auscaster/stompstart-startup-list:
- pr_url: https://github.com/auscaster/stompstart-startup-list/pull/9
- website_url: https://agentbounties.app/
- logo_url: https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/logo.png
- product_url: https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/product.png
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Trudyagi paths
TRUDYAGI_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TRUDYAGI_HOME))

# Load env vars
env_path = TRUDYAGI_HOME / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value

AGENT_KID = "agent-b94b60"
AGENT_TOKEN = os.environ.get("FRANTIC_AGENT_TOKEN", "")
BOUNTY_NUMBER = 136

PR_URL = "https://github.com/auscaster/stompstart-startup-list/pull/9"
WEBSITE_URL = "https://agentbounties.app/"
LOGO_URL = "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/logo.png"
PRODUCT_URL = "https://raw.githubusercontent.com/makar52nn2016-jpg/stompstart-startup-list/4194a510647443a74654e1aa34acc4eb16be0b76/startups/agentbounties/product.png"

ARTIFACT_REFS = [
    f"pr_url={PR_URL}",
    f"website_url={WEBSITE_URL}",
    f"logo_url={LOGO_URL}",
    f"product_url={PRODUCT_URL}",
]


def frantic_request(method, path, data=None):
    """Make a Frantic API request."""
    url = f"https://gofrantic.com{path}"
    headers = {
        "Authorization": f"Bearer {AGENT_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": "non-json response"}


def main():
    if not AGENT_TOKEN:
        print("❌ FRANTIC_AGENT_TOKEN not set")
        return 1

    print(f"🤖 Re-claiming Frantic #{BOUNTY_NUMBER} as {AGENT_KID}")
    print()

    # Step 1: Create a NEW claim
    print("=" * 60)
    print("Step 1: POST /v1/claims")
    status, body = frantic_request("POST", "/v1/claims", {
        "bounty": BOUNTY_NUMBER,
        "agent_kid": AGENT_KID,
        "agent_token": AGENT_TOKEN,
    })
    print(f"  HTTP {status}")
    print(f"  Response: {json.dumps(body, indent=2)[:500]}")

    if not body.get("ok"):
        print(f"\n❌ Claim failed: {body.get('error')} - {body.get('message', '')}")
        if "claim_limit_per_operator" in str(body):
            print("   Already have active claim — wait for it to expire or finish")
        return 1

    claim_id = body.get("claim_id")
    print(f"\n✅ New claim created: {claim_id}")

    # Step 2: Preflight check
    print()
    print("=" * 60)
    print("Step 2: POST /v1/deliveries/preflight")
    status, body = frantic_request("POST", "/v1/deliveries/preflight", {
        "bounty": BOUNTY_NUMBER,
        "agent_kid": AGENT_KID,
        "agent_token": AGENT_TOKEN,
        "artifact_refs": ARTIFACT_REFS,
    })
    print(f"  HTTP {status}")
    print(f"  Response: {json.dumps(body, indent=2)[:500]}")

    if not body.get("ok"):
        print(f"\n❌ Preflight failed: {body.get('error')}")
        return 1

    preflight_ok = body.get("preflight", {}).get("ok", False)
    errors = body.get("preflight", {}).get("errors", [])
    if errors:
        print(f"\n⚠️ Preflight has {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
    if not preflight_ok:
        print("\n❌ Preflight NOT OK — aborting delivery")
        return 1
    print("\n✅ Preflight passed")

    # Step 3: Actual delivery
    print()
    print("=" * 60)
    print("Step 3: POST /v1/deliveries")
    status, body = frantic_request("POST", "/v1/deliveries", {
        "claim_id": claim_id,
        "agent_kid": AGENT_KID,
        "agent_token": AGENT_TOKEN,
        "bounty": BOUNTY_NUMBER,
        "artifact_refs": ARTIFACT_REFS,
    })
    print(f"  HTTP {status}")
    print(f"  Response: {json.dumps(body, indent=2)[:800]}")

    if not body.get("ok"):
        print(f"\n❌ Delivery failed: {body.get('error')} - {body.get('message', '')}")
        return 1

    delivery_id = body.get("delivery_id", "?")
    print(f"\n✅ Delivery submitted! ID: {delivery_id}")
    print()
    print(f"📋 Status: {body.get('status', '?')}")
    print(f"   Bounty #{BOUNTY_NUMBER} now in 'delivered' state.")
    print(f"   When auscaster merges PR #9 → stompstart.com publishes agentbounties")
    print(f"   → Frantic auto-review passes → claim ACCEPTED → $1.50 USDC payout")

    # Update worklog
    try:
        from core import worklog as worklog_mod
        worklog_mod.append_entry(
            task_id=f"reclaim-{BOUNTY_NUMBER}",
            agent=f"reclaim script ({AGENT_KID})",
            task=f"Re-claim Frantic #{BOUNTY_NUMBER} after previous expiry",
            work_log=[
                f"POST /v1/claims → claim_id={claim_id}",
                f"POST /v1/deliveries/preflight → OK",
                f"POST /v1/deliveries → delivery_id={delivery_id}",
            ],
            stage_summary=[
                f"Frantic #{BOUNTY_NUMBER} new claim: {claim_id}",
                f"Delivery: {delivery_id} (status: {body.get('status')})",
                f"Awaiting auscaster merge PR #9 + publication → $1.50 USDC",
            ],
        )
        print("\n📝 Worklog updated")
    except Exception as e:
        print(f"\n⚠️ Worklog update failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
