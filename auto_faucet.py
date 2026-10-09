#!/usr/bin/env python3
"""Auto-faucet claimer - claims free crypto from multiple faucets."""
import urllib.request, json, time, webbrowser, sys, os

FAUCETS = [
    ("https://cointiply.com/claim", "Cointiply - claim every hour"),
    ("https://www.coinpayu.com/ptc", "CoinPayU - PTC ads"),
]

print("Auto-faucet claimer started!")
print(f"Wallet: wakefulneon901@walletofsatoshi.com")
print(f"USDC: 0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A")
print()

while True:
    for url, name in FAUCETS:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {name} - opening browser...")
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(60)
    print("Waiting 1 hour for next cycle...")
    time.sleep(3600)
