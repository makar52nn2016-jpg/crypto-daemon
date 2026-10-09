# 🚜 BULLDOZER MINING — BEST OPTIONS FOR PASSIVE INCOME
# Run the option that matches your hardware:

# ═══ OPTION 1: NiceHash (BEST — auto-switches to most profitable) ═══
# 1. Go to https://www.nicehash.com
# 2. Download NiceHash Miner (NHM)
# 3. Create account, add your BTC address (or Lightning wallet)
# 4. Run NHM — it auto-detects CPU+GPU and mines the most profitable coin
# 5. Payouts in BTC — can withdraw to Lightning via Wallet of Satoshi
# CPU: ~$0.01-0.05/day | GPU (RTX 3060+): ~$0.50-5.00/day

# ═══ OPTION 2: Monero (CPU only, simplest) ═══
# Already set up — see start_miner.ps1
# ~$0.01-0.05/day

# ═══ OPTION 3: Honeygain (passive bandwidth sharing) ═══
# 1. Go to https://dashboard.honeygain.com
# 2. Download Honeygain app
# 3. Sign up with email
# 4. Run — shares unused bandwidth, earns $0.10-0.50/day
# Completely passive — no mining, just bandwidth sharing

# ═══ OPTION 4: Storj (passive storage) ═══
# 1. Go to https://www.storj.io
# 2. Apply as a storage node operator
# 3. Share unused disk space, earn $5-50/month
# Requires: 8TB+ disk, 99.5% uptime, decent bandwidth

# ═══ OPTION 5: Run a Lightning node ═══
# 1. Install Lightning Terminal or Eclair
# 2. Open channels, earn routing fees
# 3. ~$0.01-0.10/day in routing fees (needs capital for channels)

# ═══ RECOMMENDED: Run NiceHash + Honeygain together ═══
# NiceHash: mines the most profitable coin (auto)
# Honeygain: shares unused bandwidth (passive)
# Combined: ~$0.50-5.50/day depending on hardware

Write-Host "🚜 BULLDOZER PASSIVE INCOME OPTIONS" -ForegroundColor Green
Write-Host ""
Write-Host "Option 1 (BEST): NiceHash" -ForegroundColor Cyan
Write-Host "  Download from: https://www.nicehash.com" -ForegroundColor White
Write-Host "  Auto-mines most profitable coin, pays in BTC" -ForegroundColor White
Write-Host ""
Write-Host "Option 2 (EASY): Honeygain" -ForegroundColor Cyan
Write-Host "  Download from: https://www.honeygain.com" -ForegroundColor White
Write-Host "  Shares bandwidth, ~$0.10-0.50/day" -ForegroundColor White
Write-Host ""
Write-Host "Option 3 (CPU): Monero" -ForegroundColor Cyan
Write-Host "  Already set up — run start_miner.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Option 4 (Storage): Storj" -ForegroundColor Cyan
Write-Host "  https://www.storj.io — share disk space, $5-50/month" -ForegroundColor White
Write-Host ""
Write-Host "RECOMMENDED: Run NiceHash + Honeygain together!" -ForegroundColor Yellow
Write-Host "Start-Process 'https://www.nicehash.com'"
Write-Host "Start-Process 'https://www.honeygain.com'"
