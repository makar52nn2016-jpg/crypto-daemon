#!/usr/bin/env powershell
# 🚜 BULLDOZER ALL-IN-ONE — starts ALL income streams on your PC
# Run: powershell -ExecutionPolicy Bypass -File start_all.ps1

Write-Host "🚜 BULLDOZER ALL-IN-ONE INCOME SYSTEM" -ForegroundColor Green
Write-Host "Starting ALL income streams..." -ForegroundColor Cyan
Write-Host ""

# 1. Nostr autoposter (posts every 15 min, earns zaps)
Write-Host "1/3 Starting Nostr autoposter..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "nostr_autoposter.py" -WindowStyle Normal

# 2. Auto-faucet (claims free crypto every hour)
Write-Host "2/3 Starting auto-faucet..." -ForegroundColor Yellow
Start-Process -FilePath "python" -ArgumentList "auto_faucet.py" -WindowStyle Normal

# 3. Monero miner (passive mining 24/7)
Write-Host "3/3 Starting Monero miner..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-ExecutionPolicy Bypass -File start_miner.ps1" -WindowStyle Normal

Write-Host ""
Write-Host "✅ ALL 3 INCOME STREAMS STARTED!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Income streams:" -ForegroundColor Cyan
Write-Host "   1. Nostr: posts every 15 min → earns Lightning zaps" -ForegroundColor White
Write-Host "   2. Faucet: claims free crypto every hour" -ForegroundColor White
Write-Host "   3. Miner: mines Monero 24/7 on CPU" -ForegroundColor White
Write-Host ""
Write-Host "⚡ Lightning wallet: wakefulneon901@walletofsatoshi.com" -ForegroundColor Cyan
Write-Host "🌊 USDC (Base): 0x53dbe1b36BA3BEAC6cEf6cD22AD50E362DBcB23A" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to close this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
