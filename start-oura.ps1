$ErrorActionPreference = 'Stop'

$RepoUrl = 'https://github.com/Noxy-HNR/Personal-health-data.git'
$InstallRoot = 'C:\AI\Personal-health-data'
$RepoRoot = $InstallRoot
$Venv = Join-Path $RepoRoot '.venv'
$EnvFile = Join-Path $RepoRoot 'oura.env'
$EnvExample = Join-Path $RepoRoot 'oura.env.example'
$Python = Join-Path $Venv 'Scripts\python.exe'
$Service = Join-Path $RepoRoot 'oura_service.py'
$HealthUrl = 'http://127.0.0.1:8765/health'
$OAuthUrl = 'http://127.0.0.1:8765/oauth/start'

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ' Oura Personal Health MCP' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''

# Clone the public repository on first run; otherwise update it.
if (-not (Test-Path (Join-Path $RepoRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $RepoRoot) | Out-Null
    Write-Host 'Downloading Oura service from GitHub...' -ForegroundColor Yellow
    git clone $RepoUrl $RepoRoot
} else {
    Write-Host 'Updating Oura service from GitHub...' -ForegroundColor Yellow
    git -C $RepoRoot pull --ff-only
}

if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host ''
    Write-Host 'Created:' $EnvFile -ForegroundColor Green
    Write-Host 'Enter your Oura Client ID and Client Secret in that file.' -ForegroundColor Yellow
    Write-Host 'The file is git-ignored and will NOT be uploaded to GitHub.' -ForegroundColor Green
    Write-Host ''
    Start-Process notepad.exe -ArgumentList $EnvFile

    while ($true) {
        Start-Sleep -Seconds 2
        $text = Get-Content $EnvFile -Raw
        $ready = ($text -match 'OURA_CLIENT_ID=(?!PASTE_YOUR_OURA_CLIENT_ID_HERE).+') -and
                 ($text -match 'OURA_CLIENT_SECRET=(?!PASTE_YOUR_OURA_CLIENT_SECRET_HERE).+')
        if ($ready) { break }
        Write-Host 'Waiting for Oura credentials to be entered and saved...' -ForegroundColor DarkYellow
    }
}

# Create the Python environment once.
if (-not (Test-Path $Python)) {
    Write-Host 'Creating Python virtual environment...' -ForegroundColor Yellow
    python -m venv $Venv
}

Write-Host 'Installing/updating Python dependencies...' -ForegroundColor Yellow
& $Python -m pip install --upgrade pip --disable-pip-version-check | Out-Host
& $Python -m pip install -r (Join-Path $RepoRoot 'requirements.txt') --disable-pip-version-check | Out-Host

# Keep local credentials readable by the current Windows user only.
try {
    icacls $EnvFile /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null
} catch {
    Write-Host 'Could not tighten credential-file ACL; continuing.' -ForegroundColor DarkYellow
}

# Start the service in a separate PowerShell window so this launcher remains usable.
Write-Host 'Starting Oura MCP service on 127.0.0.1:8765...' -ForegroundColor Green
Start-Process powershell.exe -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-Command', "Set-Location '$RepoRoot'; & '$Python' '$Service'"
)

Write-Host 'Waiting for service...' -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        if ($response.status -eq 'ok') {
            $healthy = $true
            break
        }
    } catch {}
}

if (-not $healthy) {
    Write-Host 'Service did not become healthy within 30 seconds.' -ForegroundColor Red
    Write-Host "Try: $HealthUrl" -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host 'Oura MCP is running.' -ForegroundColor Green
Write-Host 'MCP endpoint: http://127.0.0.1:8765/mcp' -ForegroundColor Cyan
Write-Host 'Health:       http://127.0.0.1:8765/health' -ForegroundColor Cyan
Write-Host 'OAuth:        http://127.0.0.1:8765/oauth/start' -ForegroundColor Cyan
Write-Host ''

$status = Invoke-RestMethod -Uri $HealthUrl
if (-not $status.authorized) {
    Write-Host 'Oura is not authorized yet. Opening the OAuth page...' -ForegroundColor Yellow
    Start-Process $OAuthUrl
} else {
    Write-Host 'Oura is already authorized. Existing local token will be reused/refreshed.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Connect your cptr/Open WebUI MCP client to:' -ForegroundColor Magenta
Write-Host 'http://127.0.0.1:8765/mcp' -ForegroundColor White
Write-Host ''
