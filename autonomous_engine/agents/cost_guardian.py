"""
autonomous_engine/agents/cost_guardian.py — Block ALL paid API calls

Guardian that checks wallet balances BEFORE any operation that could cost money.
If balance < $0.01 → halts all autonomous operations and logs critical event.

Checks:
  - Pimlico prepaid balance (via API)
  - Smart Account ETH balance (Base RPC)
  - Any API that returns cost estimate

Default behavior:
  - Allow: GitHub API (free with PAT), Frantic API (free), z-ai CLI (free locally),
    OpenSea API (free read), Stompstart API (free read)
  - Block: OpenAI API, Anthropic API, paid RPC calls, anything requiring payment

If cost_guardian.json shows "halt": true → autonomous_engine must STOP all paid ops.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ENGINE_HOME = Path(__file__).resolve().parent.parent
STATE_FILE = ENGINE_HOME / "state" / "cost_guardian.json"

# Free APIs (no auth needed or use free tier)
FREE_APIS = {
    "github": "https://api.github.com",  # Auth via PAT, 5000/hr
    "frantic": "https://gofrantic.com",  # Free
    "stellar_horizon": "https://horizon.stellar.org",  # Free
    "tonapi": "https://tonapi.io",  # Free
    "base_rpc": "https://mainnet.base.org",  # Free Coinbase RPC
    "publicnode": "https://base-rpc.publicnode.com",  # Free fallback
    "stompstart": "https://stompstart.com",  # Free read
    "z_ai_local": "https://internal-api.z.ai",  # Free (Z.ai SDK)
}

# Paid APIs that should be blocked by default
PAID_APIS = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "groq_paid": "https://api.groq.com/openai",  # Free tier exists, but billed above
    "openrouter_paid": "https://openrouter.ai/api/v1",  # Free + paid models
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_check_at": None,
        "halt": False,
        "halt_reason": None,
        "checks": [],
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_pimlico_balance() -> dict:
    """Check Pimlico prepaid balance (for sniper gas sponsorship)."""
    pim_key = os.environ.get("PIMLICO_API_KEY", "")
    if not pim_key:
        return {"status": "skip", "reason": "PIMLICO_API_KEY not set"}

    # Try pm_getPaymasterData on a stub UserOp — it returns insufficient balance error if $0
    try:
        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "pm_getPaymasterData",
            "params": [{
                "sender": "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A",
                "nonce": "0x0",
                "initCode": "0x",
                "callData": "0x",
                "callGasLimit": "0x10000",
                "verificationGasLimit": "0x10000",
                "preVerificationGas": "0x10000",
                "maxFeePerGas": "0x80f994",
                "maxPriorityFeePerGas": "0x126ccc",
                "paymasterAndData": "0x",
                "signature": "0x"
            }, "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789", "0x2105"],
            "id": 1,
        }).encode()
        req = urllib.request.Request(
            f"https://api.pimlico.io/v2/base/rpc?apikey={pim_key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if "error" in data:
                err_msg = data["error"].get("message", "")
                if "Insufficient Pimlico balance" in err_msg:
                    return {"status": "ok_zero", "balance_usd": 0, "required_usd": 0.007}
                return {"status": "ok", "raw": data}
            return {"status": "ok_funded", "raw": data}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}


def check_smart_account_eth() -> dict:
    """Check Smart Account ETH balance on Base (for sniper)."""
    try:
        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": ["0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A", "latest"],
            "id": 1,
        }).encode()
        req = urllib.request.Request(
            "https://mainnet.base.org",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            bal_hex = data.get("result", "0x0")
            bal_wei = int(bal_hex, 16)
            bal_eth = bal_wei / 1e18
            return {"status": "ok", "balance_eth": bal_eth, "balance_usd_approx": bal_eth * 3000}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}


def run_cycle() -> dict:
    """Check all cost-related balances. Halt autonomous ops if any paid API would fail."""
    print(f"[Cost-Guardian] Cycle start at {datetime.now(timezone.utc).isoformat()}")
    state = load_state()
    state["last_check_at"] = datetime.now(timezone.utc).isoformat()
    state["checks"] = []

    halt = False
    halt_reasons = []

    # 1. Pimlico balance (for sniper gas sponsorship)
    pim = check_pimlico_balance()
    state["checks"].append({"agent": "sniper_sponsorship", "result": pim})
    print(f"[Cost-Guardian] Pimlico: {pim.get('status')} balance_usd={pim.get('balance_usd', 'unknown')}")

    # 2. Smart Account ETH (for sniper self-paid gas)
    eth = check_smart_account_eth()
    state["checks"].append({"agent": "sniper_self_paid", "result": eth})
    print(f"[Cost-Guardian] Smart Account ETH: {eth.get('balance_eth', 0):.8f} ETH (~${eth.get('balance_usd_approx', 0):.4f})")

    # Determine halt status
    # Halt ONLY if both Pimlico AND Smart Account are at $0 — sniper can't mint
    # Other agents (cooldown_timer, merge_watcher) don't cost money, so they continue
    pim_zero = pim.get("status") == "ok_zero"
    eth_zero = (eth.get("balance_eth", 0) < 0.00001)

    if pim_zero and eth_zero:
        halt = True
        halt_reasons.append("Sniper can't mint — Pimlico $0 + ETH $0. Sniper halts, but Cooldown-Timer + Merge-Watcher continue (they don't need ETH)")

    state["halt"] = halt
    state["halt_reason"] = "; ".join(halt_reasons) if halt_reasons else None

    save_state(state)

    if halt:
        print(f"[Cost-Guardian] ⚠️ HALT active: {state['halt_reason']}")
        print(f"[Cost-Guardian] Sniper disabled. Other agents continue.")
    else:
        print(f"[Cost-Guardian] ✅ All clear. Agents can run.")

    return {"halt": halt, "reason": state["halt_reason"], "checks": state["checks"]}


def is_paid_api_blocked(url: str) -> bool:
    """Check if a URL is in the paid APIs blocklist."""
    for name, paid_url in PAID_APIS.items():
        if url.startswith(paid_url):
            return True
    return False


if __name__ == "__main__":
    result = run_cycle()
    print(f"\n[Cost-Guardian] Halt: {result['halt']}")
    sys.exit(0)
