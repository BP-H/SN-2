Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "      SuperNova 2177 Unified Launcher     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Which Frontend would you like to launch?"
Write-Host "  1. Next.js (retired/off-path; use Social Seven)" -ForegroundColor DarkGray
Write-Host "  2. Vite Professional (retired/off-path; use Social Seven)" -ForegroundColor DarkGray
Write-Host "  3. Vite 3D (retired/off-path; use Social Seven)" -ForegroundColor DarkGray
Write-Host "  4. Vite Basic (legacy/off-path)" -ForegroundColor White
Write-Host "  5. Frontend Nova (deleted/off-path; use Social Seven)" -ForegroundColor DarkGray
Write-Host "  6. Social Six (legacy/off-path)" -ForegroundColor Blue
Write-Host "  7. Social Seven (Active/default FE7)" -ForegroundColor Magenta
Write-Host ""

$choice = Read-Host "Enter a number (1-7) or press Enter for Social Seven"

if ([string]::IsNullOrWhiteSpace($choice)) {
    $choice = "7"
}

$frontendMap = @{
    "1" = "__retired_frontend_next"
    "2" = "__retired_frontend_professional"
    "3" = "__retired_frontend_vite_3d"
    "4" = "frontend-vite-basic"
    "5" = "__retired_frontend_nova"
    "6" = "frontend-social-six"
    "7" = "frontend-social-seven"
}

$frontendPorts = @{
    "frontend-vite-basic" = 5174
    "frontend-social-six" = 3001
    "frontend-social-seven" = 3007
}

$frontendDir = $frontendMap[$choice]

if ($null -eq $frontendDir) {
    Write-Host "Invalid choice. Exiting." -ForegroundColor Red
    exit 1
}

if ($frontendDir -eq "__retired_frontend_nova" -or $frontendDir -eq "__retired_frontend_professional" -or $frontendDir -eq "__retired_frontend_vite_3d" -or $frontendDir -eq "__retired_frontend_next") {
    if ($frontendDir -eq "__retired_frontend_nova") {
        Write-Host "`nfrontend-nova was deleted after retirement. Use frontend-social-seven." -ForegroundColor Yellow
    } elseif ($frontendDir -eq "__retired_frontend_professional") {
        Write-Host "`nfrontend-professional local launchers were retired after cleanup checks. Use frontend-social-seven." -ForegroundColor Yellow
    } elseif ($frontendDir -eq "__retired_frontend_next") {
        Write-Host "`nfrontend-next local launchers were retired pending deployment/auth/security audit. Use frontend-social-seven." -ForegroundColor Yellow
    } else {
        Write-Host "`nfrontend-vite-3d was deleted after launcher retirement. Use frontend-social-seven." -ForegroundColor Yellow
    }
    Write-Host "Run this launcher again and choose option 7 for Social Seven." -ForegroundColor Cyan
    exit 0
}

Write-Host "`n[1/2] Starting Backend in a new window..." -ForegroundColor Cyan
$repoPath = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start the backend in a separate PowerShell window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$repoPath'; Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass; .\.venv\Scripts\Activate.ps1; python -m uvicorn app:app --host 0.0.0.0 --port 8000"

Write-Host "[2/2] Starting Frontend: $frontendDir..." -ForegroundColor Cyan

# Start the frontend in the current window
Set-Location "$repoPath\$frontendDir"
if ($frontendDir -eq "frontend-social-six" -or $frontendDir -eq "frontend-social-seven") {
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
    & "C:\Program Files\nodejs\npm.cmd" run dev
} else {
    $env:VITE_API_URL = "http://127.0.0.1:8000"
    $port = $frontendPorts[$frontendDir]
    & "C:\Program Files\nodejs\npm.cmd" run dev -- --host 0.0.0.0 --port $port
}
