# 回响计划 · 启动脚本 (PowerShell)
# 自动启动 llama-server + Echo CLI

# 修复中文乱码
chcp 65001 > $null
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$MODEL = "E:\Models\gemma\gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
$LLAMA = "D:\llama-b9568-bin-win-cuda-12.4-x64\llama-server.exe"
$PORT = 8080

Write-Host "=== 回响计划 · Project Echo ===" -ForegroundColor Yellow
Write-Host ""

# 1. 启动 llama-server（后台进程）
Write-Host "[1/2] 启动模型服务 …" -ForegroundColor Cyan
$server = Start-Process -FilePath $LLAMA -ArgumentList @(
    "-m", $MODEL,
    "--host", "127.0.0.1",
    "--port", $PORT,
    "-c", "8192",
    "-ngl", "99",
    "--reasoning", "off"
) -PassThru -WindowStyle Hidden

# 2. 等待服务就绪
Write-Host "      等待模型加载 …" -ForegroundColor DarkGray
do {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/v1/models" -TimeoutSec 2 -ErrorAction Stop
        $ready = $true
    } catch {
        $ready = $false
    }
} until ($ready)

Write-Host "      模型就绪" -ForegroundColor Green
Write-Host ""

# 3. 启动 Echo CLI
Write-Host "[2/2] 唤醒回响 …" -ForegroundColor Cyan
python -m echo.cli

# 4. 清理
Write-Host ""
Write-Host "关闭模型服务 …" -ForegroundColor DarkGray
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
Write-Host "完成" -ForegroundColor Green
