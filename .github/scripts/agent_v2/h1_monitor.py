#!/usr/bin/env python3
"""HackerOne Directory Monitor — scans for new Web3/crypto bounty programs.
Uses Playwright (headless Chromium) to bypass Cloudflare protection.
Alerts via Telegram when new targets appear.
"""
import asyncio, json, os, re, urllib.request

SEEN_FILE = "logs/seen_h1_programs.json"
TARGET_KEYWORDS = ["crypto", "blockchain", "web3", "defi", "smart contract",
                   "ethereum", "base", "solana", "wallet", "nft", "bitcoin",
                   "lightning", "bridge", "swap", "staking", "lending",
                   "protocol", "token", "dao", "governance", "oracle"]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return []

def save_seen(programs):
    os.makedirs(os.path.dirname(SEEN_FILE) or '.', exist_ok=True)
    with open(SEEN_FILE, 'w') as f:
        json.dump(programs, f, indent=2)

def send_telegram(message):
    token = os.getenv('TG_TOKEN', '')
    chat = os.getenv('TG_CHAT', '')
    if not token or not chat:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat, "text": message, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"Telegram alert sent: {r.status}")
    except Exception as e:
        print(f"Telegram err: {e}")

async def scan_hackerone():
    print("🕵️ Scanning HackerOne directory for Web3/crypto programs...")
    seen = load_seen()
    new_targets = []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        os.system(f"pip install playwright --quiet 2>&1")
        os.system("playwright install chromium 2>&1")
        from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navigate to HackerOne directory
            await page.goto("https://hackerone.com/directory/programs",
                          wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)  # React render time

            # Extract all program links
            links = await page.locator('a[href*="/"]').all()
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()

                    if not href or not href.startswith("/hacker"):
                        continue
                    parts = href.strip("/").split("/")
                    if len(parts) != 2:
                        continue

                    name = parts[1]
                    text_lower = text.lower()

                    # Check for Web3/crypto keywords
                    if any(kw in text_lower for kw in TARGET_KEYWORDS):
                        if name not in seen:
                            new_targets.append({
                                "name": name,
                                "url": f"https://hackerone.com{href}",
                                "snippet": text[:200].replace('\n', ' ')
                            })
                            seen.append(name)
                except:
                    continue

            # Also try scrolling to load more programs
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 2000)")
                await page.wait_for_timeout(2000)

            # Re-scan after scroll
            links2 = await page.locator('a[href*="/"]').all()
            for link in links2:
                try:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if not href or not href.startswith("/hacker"):
                        continue
                    parts = href.strip("/").split("/")
                    if len(parts) != 2:
                        continue
                    name = parts[1]
                    text_lower = text.lower()
                    if any(kw in text_lower for kw in TARGET_KEYWORDS):
                        if name not in seen:
                            new_targets.append({
                                "name": name,
                                "url": f"https://hackerone.com{href}",
                                "snippet": text[:200].replace('\n', ' ')
                            })
                            seen.append(name)
                except:
                    continue

        except Exception as e:
            print(f"⚠️ Scan error (Cloudflare?): {e}")
        finally:
            await browser.close()

    save_seen(seen)

    if new_targets:
        print(f"\n🚨 FOUND {len(new_targets)} NEW WEB3 TARGETS!")
        msg = f"🚨 *{len(new_targets)} new Web3 bounty targets on HackerOne!*\n\n"
        for t in new_targets[:10]:
            print(f"\n🎯 {t['name']}")
            print(f"🔗 {t['url']}")
            print(f"📝 {t['snippet'][:100]}")
            msg += f"🎯 [{t['name']}]({t['url']})\n{t['snippet'][:80]}\n\n"
        send_telegram(msg)
    else:
        print("✅ No new Web3 programs found.")

    return new_targets

if __name__ == "__main__":
    asyncio.run(scan_hackerone())
