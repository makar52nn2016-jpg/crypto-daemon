# Monero (XMR) CPU Miner — earns ~$0.01-0.05/day passive income
# Run: powershell -ExecutionPolicy Bypass -File start_miner.ps1
# Payment wallet: 48Q7T5mN5eR3y2KqBw8m8Yq2cWQkLf3v9j5xB4HsN6Qr9tZ1w
# (Replace with YOUR XMR address from cakewallet.com or monero-wallet)

Write-Host "🚜 Starting Monero CPU Miner..." -ForegroundColor Green
Write-Host "   Pool: supportxmr.com:3333" -ForegroundColor Cyan
Write-Host "   Payment: see config below" -ForegroundColor Cyan

$url = "https://github.com/xmrig/xmrig/releases/download/v6.21.0/xmrig-6.21.0-msvc-win64.zip"
$zip = "$env:TEMP\xmrig.zip"
$dir = "$env:TEMP\xmrig"

if (-not (Test-Path "$dir\xmrig-6.21.0-msvc-win64\xmrig.exe")) {
    Write-Host "Downloading XMRig..."
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    Write-Host "Downloaded!"
}

# CONFIG: Replace with your Monero address
$WALLET = "48Q7T5mN5eR3y2KqBw8m8Yq2cWQkLf3v9j5xB4HsN6Qr9tZ1w"

Write-Host "Starting miner... Press Ctrl+C to stop."
& "$dir\xmrig-6.21.0-msvc-win64\xmrig.exe" -o pool.supportxmr.com:3333 -u $WALLET -p x --donate-level 1 --cpu-max-threads=2
