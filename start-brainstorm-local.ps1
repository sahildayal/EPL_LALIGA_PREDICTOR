# Local Brainstorm Server Starter for Windows
# Run this file in PowerShell: powershell -ExecutionPolicy Bypass -File .\start-brainstorm-local.ps1

$sessionDir = "C:\Users\Bikash\Desktop\CODEBASE\WorldCupPredictor\.superpowers\brainstorm\session"
if (!(Test-Path "$sessionDir\content")) { New-Item -ItemType Directory -Force -Path "$sessionDir\content" }
if (!(Test-Path "$sessionDir\state")) { New-Item -ItemType Directory -Force -Path "$sessionDir\state" }

# Set Environment Variables for the Node Server
$env:BRAINSTORM_DIR = $sessionDir
$env:BRAINSTORM_HOST = "127.0.0.1"
$env:BRAINSTORM_URL_HOST = "localhost"
$env:BRAINSTORM_OWNER_PID = ""
$env:BRAINSTORM_OPEN = "1"
$env:BRAINSTORM_PORT = "59161"
$env:BRAINSTORM_TOKEN = "89c7cf16c2d67ea563954d5a063ae9d82466e572e58ba0dcdd5bad83790d2ed1"

Write-Host "--------------------------------------------------------" -ForegroundColor Green
Write-Host "🚀 Launching Local Brainstorm Server..." -ForegroundColor Green
Write-Host "URL: http://localhost:59161/?key=89c7cf16c2d67ea563954d5a063ae9d82466e572e58ba0dcdd5bad83790d2ed1" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Green

# Automatically open browser
Start-Process "http://localhost:59161/?key=89c7cf16c2d67ea563954d5a063ae9d82466e572e58ba0dcdd5bad83790d2ed1"

# Run Node Server
node "C:\Users\Bikash\.gemini\config\plugins\superpowers\skills\brainstorming\scripts\server.cjs"
