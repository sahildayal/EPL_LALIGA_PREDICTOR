# local web server starter for the World Cup Predictor Dashboard
# Run this file in PowerShell: powershell -ExecutionPolicy Bypass -File .\start-dashboard.ps1

Write-Host "--------------------------------------------------------" -ForegroundColor Green
Write-Host "🚀 Launching Local Web Server for World Cup Dashboard..." -ForegroundColor Green
Write-Host "Port: 8080" -ForegroundColor Green
Write-Host "URL: http://localhost:8080/dashboard.html" -ForegroundColor Cyan
Write-Host "--------------------------------------------------------" -ForegroundColor Green

# Automatically open browser
Start-Process "http://localhost:8080/dashboard.html"

# Run Python built-in HTTP server
python -m http.server 8080
