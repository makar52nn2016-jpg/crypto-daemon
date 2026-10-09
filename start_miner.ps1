# Monero (XMR) CPU Miner --- earns $0.10-0.50/day with REAL XMR address
# Run: powershell -ExecutionPolicy Bypass -File start_miner.ps1
#
# *** ACTION REQUIRED ***
# Replace the FAKE placeholder below with your REAL Monero address.
# Get one free at https://cakewallet.com/ (95 chars, starts with "4")
#
# This script downloads XMRig and starts mining on supportxmr.com pool.
# Earnings accumulate to your wallet every ~10 min when block is found.

$WALLET = "REPLACE_WITH_YOUR_REAL_XMR_ADDRESS_95_CHARS_STARTING_WITH_4"

if ($WALLET -like "REPLACE*") {
    Write-Host "ERROR: Wallet address not set." -ForegroundColor Red
    Write-Host "1. Go to https://cakewallet.com/" -ForegroundColor Yellow
    Write-Host "2. Install Cake Wallet (iOS/Android/desktop)" -ForegroundColor Yellow
    Write-Host "3. Create new wallet, write down seed phrase" -ForegroundColor Yellow
    Write-Host "4. Copy receive address (95 chars, starts with '4')" -ForegroundColor Yellow
    Write-Host "5. Edit this file, replace the placeholder" -ForegroundColor Yellow
    Write-Host "6. Re-run this script" -ForegroundColor Yellow
    exit 1
}

Write-Host "---- Starting Monero CPU Miner ----" -ForegroundColor Green
Write-Host "   Pool: supportxmr.com:3333" -ForegroundColor Cyan
Write-Host "   Wallet: $WALLET" -ForegroundColor Cyan
Write-Host "   Expected: $0.10-0.50/day on standard CPU" -ForegroundColor Cyan
Write-Host ""

$url = "https://github.com/xmrig/xmrig/releases/download/v6.21.0/xmrig-6.21.0-msvc-win64.zip"
$zip = "$env:TEMP\xmrig.zip"
$dir = "$env:TEMP\xmrig"

if (-not (Test-Path "$dir\xmrig-6.21.0-msvc-win64\xmrig.exe")) {
    Write-Host "Downloading XMRig..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    Write-Host "Downloaded!" -ForegroundColor Green
}

Write-Host "Starting miner on all CPU cores... Press Ctrl+C to stop." -ForegroundColor Green
Write-Host "Monitor: https://supportxmr.com/#/miner/$WALLET" -ForegroundColor Cyan
Write-Host ""

& "$dir\xmrig-6.21.0-msvc-win64\xmrig.exe" -o pool.supportxmr.com:3333 -u $WALLET -p x --donate-level 1
