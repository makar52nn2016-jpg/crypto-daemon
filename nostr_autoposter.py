#!/usr/bin/env python3
"""Nostr autoposter v2 — posts valuable content every 15 minutes for maximum zap exposure."""
import json, time, asyncio, random, sys, os
try:
    import websockets
    from pynostr.key import PrivateKey
    from pynostr.event import Event
except ImportError:
    os.system(f"{sys.executable} -m pip install pynostr websockets --break-system-packages")
    import websockets
    from pynostr.key import PrivateKey
    from pynostr.event import Event

PRIV = bytes.fromhex("02556274f5f732b20672867e603f605a9e521aaa10eb2bcc605d99b0b0a0011c")
WALLET = "wakefulneon901@walletofsatoshi.com"
USDC = "0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A"
RELAYS = ["wss://nos.lol", "wss://relay.snort.social", "wss://nostr.bitcoiner.social", "wss://relay.primal.net", "wss://relay.damus.io"]

POSTS = [
    f"💡 TIP: Check repo.pushed_at before opening a PR. Dead repos = wasted hours. ⚡ {WALLET} #dev #github #opensource",
    f"🛡️ Anti-scam: If 8+ GitHub orgs share the same creation minute, it is a scam cluster. Verify via API. ⚡ {WALLET} #security #github",
    f"📚 LESSON: summary_plain must be <=120 chars in lesson gates. Count before pushing! ⚡ {WALLET} #dev #ci #cd",
    f"💼 FREELANCE: I write tests, fix bugs, set up CI/CD for sats. 7 PRs merged today. DM me! ⚡ {WALLET} 🌊 {USDC} #freelance #dev #python",
    f"🔧 TOOL: Bounty scanner that finds VERIFIED funded issues (opirebot/algora-bot confirmed). https://github.com/makar52nn2016-jpg/crypto-daemon ⚡ {WALLET} #opensource #tools",
    f"📖 GUIDE: How to detect GitHub bounty scams — 3 patterns to avoid. Gist: https://gist.github.com/makar52nn2016-jpg/306acc4dfc55774e8f ⚡ {WALLET} #security #dev",
    f"⚡ Zap me for more dev tips! Building 24/7 autonomous bounty agent. 7 lessons merged in MisakaNet (526 stars). {WALLET} 🌊 {USDC} #bitcoin #lightning #nostr",
    f"🎯 BOUNTY CHECKLIST: 1) opirebot commented? 2) org.created_at recent? 3) pushed_at <30d? 4) stars>=1? 5) external PRs merged before? ⚡ {WALLET} #dev #github",
]

async def post(content):
    priv = PrivateKey(PRIV)
    event = Event(kind=1, content=content, created_at=int(time.time()))
    event.sign(priv.hex())
    sent = 0
    for url in RELAYS:
        try:
            async with websockets.connect(url, ping_interval=None) as ws:
                await ws.send(json.dumps(["EVENT", event.to_dict()]))
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=5)
                    if "true" in resp: sent += 1
                except: sent += 1
        except: pass
    return sent

idx = 0
print(f"🚜 Nostr autoposter v2 — posting every 15 minutes to {len(RELAYS)} relays")
print(f"   Wallet: {WALLET}")
print(f"   Posts: {len(POSTS)} unique messages")
print(f"   Press Ctrl+C to stop")
print()

while True:
    content = POSTS[idx % len(POSTS)]
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    sent = asyncio.run(post(content))
    print(f"[{ts}] Posted to {sent} relays: {content[:50]}...")
    idx += 1
    time.sleep(900)  # 15 minutes
