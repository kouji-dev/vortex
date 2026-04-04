# Run Playwright after verifying the E2E API is up. Start the stack separately:
#   Git Bash: ./scripts/e2e-up.sh
# Optional: SKIP_E2E_STACK_CHECK=1 to skip the health check.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:SKIP_E2E_STACK_CHECK -ne "1") {
    $base = if ($env:E2E_API_URL) { $env:E2E_API_URL.TrimEnd("/") } else { "http://127.0.0.1:8001" }
    try {
        Invoke-WebRequest -Uri "$base/health" -UseBasicParsing -TimeoutSec 3 | Out-Null
    } catch {
        Write-Host "E2E API not reachable at $base/health." -ForegroundColor Red
        Write-Host "Start it from this worktree (Git Bash recommended): ./scripts/e2e-up.sh" -ForegroundColor Yellow
        Write-Host "Or set SKIP_E2E_STACK_CHECK=1 if it is already running." -ForegroundColor Yellow
        exit 1
    }
}

pnpm --dir frontend test:e2e @args
