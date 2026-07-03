# Echo Project Startup Script
# Launches llama-server + Echo CLI

$MODEL = 'E:\Models\gemma\gemma-4-12B-it-qat-UD-Q4_K_XL.gguf'
$LLAMA = 'D:\llama-b9568-bin-win-cuda-12.4-x64\llama-server.exe'
$PORT = 8080

Write-Host '=== Project Echo ===' -ForegroundColor Yellow
Write-Host ''

Write-Host '[1/2] Starting model server ...' -ForegroundColor Cyan
$server = Start-Process -FilePath $LLAMA -ArgumentList @(
    '-m', $MODEL,
    '--host', '127.0.0.1',
    '--port', $PORT,
    '-c', '98304',
    '-ngl', '99',
    '--jinja'
) -PassThru -WindowStyle Hidden

Write-Host '      Waiting for model to load ...' -ForegroundColor DarkGray
$timeout = 120
$elapsed = 0
do {
    Start-Sleep -Seconds 2
    $elapsed += 2
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:${PORT}/v1/models" -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
    } catch {
        $ready = $false
    }
    if ($elapsed -ge $timeout) {
        Write-Host '      ERROR: Model failed to load within 120s' -ForegroundColor Red
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        exit 1
    }
} until ($ready)

Write-Host '      Model ready' -ForegroundColor Green
Write-Host ''

Write-Host '[2/2] Waking Echo ...' -ForegroundColor Cyan
python -m echo.cli

Write-Host ''
Write-Host 'Shutting down model server ...' -ForegroundColor DarkGray
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
Write-Host 'Done' -ForegroundColor Green