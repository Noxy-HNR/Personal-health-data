[CmdletBinding()]
param(
    [ValidateSet('Start','Setup','Update','Stop','Status')]
    [string]$Mode = 'Start'
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/Noxy-HNR/Personal-health-data.git'
$Root = 'C:\AI\Personal-health-data'
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$EnvFile = Join-Path $Root 'oura.env'
$Example = Join-Path $Root 'oura.env.example'
$Service = Join-Path $Root 'health_mcp.py'
$Port = 8765
$HealthUrl = "http://127.0.0.1:$Port/health"
$McpUrl = "http://127.0.0.1:$Port/mcp"
$OAuthUrl = "http://127.0.0.1:$Port/oauth/start"

function Write-Header($text) {
    Write-Host ''
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host " Personal Health MCP - $text" -ForegroundColor Cyan
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host ''
}

function Ensure-Repo {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required. Install Git for Windows and run this script again.' }
    if (-not (Test-Path (Join-Path $Root '.git'))) {
        New-Item -ItemType Directory -Force -Path (Split-Path $Root) | Out-Null
        Write-Host 'Downloading Personal Health MCP...' -ForegroundColor Yellow
        git clone $RepoUrl $Root | Out-Host
    } elseif ($Mode -in @('Start','Setup','Update')) {
        Write-Host 'Updating Personal Health MCP...' -ForegroundColor Yellow
        git -C $Root pull --ff-only | Out-Host
    }
}

function Ensure-Config {
    if (-not (Test-Path $Example)) { throw "Missing configuration template: $Example" }
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $Example $EnvFile
        Write-Host "Created $EnvFile" -ForegroundColor Green
        Write-Host 'Enter your Oura Client ID and Client Secret, save the file, then close Notepad.' -ForegroundColor Yellow
        Start-Process notepad.exe -ArgumentList $EnvFile -Wait
    }
    $text = Get-Content $EnvFile -Raw
    if (($text -notmatch 'OURA_CLIENT_ID=(?!PASTE_YOUR_OURA_CLIENT_ID_HERE).+') -or ($text -notmatch 'OURA_CLIENT_SECRET=(?!PASTE_YOUR_OURA_CLIENT_SECRET_HERE).+')) {
        Write-Host "Oura credentials are not configured in $EnvFile." -ForegroundColor Yellow
        Start-Process notepad.exe -ArgumentList $EnvFile -Wait
        $text = Get-Content $EnvFile -Raw
        if (($text -notmatch 'OURA_CLIENT_ID=(?!PASTE_YOUR_OURA_CLIENT_ID_HERE).+') -or ($text -notmatch 'OURA_CLIENT_SECRET=(?!PASTE_YOUR_OURA_CLIENT_SECRET_HERE).+')) {
            throw 'Oura credentials were not configured. Nothing was started.'
        }
    }
    try { icacls $EnvFile /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null } catch { Write-Host 'Could not tighten credential-file ACL; continuing.' -ForegroundColor DarkYellow }
}

function Ensure-Python {
    if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Test-Path $Py)) { throw 'Python 3 is required. Install Python and run this script again.' }
    if (-not (Test-Path $Py)) {
        Write-Host 'Creating Python virtual environment...' -ForegroundColor Yellow
        python -m venv $Venv
    }
    Write-Host 'Installing/updating dependencies...' -ForegroundColor Yellow
    & $Py -m pip install --upgrade pip --disable-pip-version-check | Out-Host
    & $Py -m pip install -r (Join-Path $Root 'requirements.txt') --disable-pip-version-check | Out-Host
}

function Get-Health {
    try { return Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3 } catch { return $null }
}

function Stop-Service {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$Service*" }
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host 'Personal Health MCP stopped.' -ForegroundColor Green
}

if ($Mode -eq 'Stop') {
    Write-Header 'Stop'
    Stop-Service
    exit 0
}

if ($Mode -eq 'Status') {
    Write-Header 'Status'
    $s = Get-Health
    if ($null -eq $s) { Write-Host 'Service: STOPPED / unreachable' -ForegroundColor Red; exit 1 }
    Write-Host "Service:    RUNNING" -ForegroundColor Green
    Write-Host "MCP:        $McpUrl" -ForegroundColor Cyan
    Write-Host "Authorized: $($s.authorized)" -ForegroundColor Cyan
    Write-Host "Health:     $HealthUrl" -ForegroundColor Cyan
    exit 0
}

Write-Header 'Setup' 
Ensure-Repo
Ensure-Config
Ensure-Python

if ($Mode -eq 'Update') {
    Write-Host 'Update complete. Service was not restarted.' -ForegroundColor Green
    exit 0
}

$current = Get-Health
if ($null -ne $current) {
    Write-Host "Personal Health MCP is already running on port $Port." -ForegroundColor Green
    if (-not $current.authorized) { Start-Process $OAuthUrl }
    exit 0
}

Write-Host "Starting Personal Health MCP on 127.0.0.1:$Port..." -ForegroundColor Green
$cmd = "Set-Location '$Root'; & '$Py' '$Service'"
Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$cmd) -WindowStyle Normal

$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    $s = Get-Health
    if ($null -ne $s -and $s.status -eq 'ok') { $healthy = $true; break }
}

if (-not $healthy) {
    Write-Host 'Service did not become healthy within 45 seconds.' -ForegroundColor Red
    Write-Host "Check: $HealthUrl" -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host 'Personal Health MCP is running.' -ForegroundColor Green
Write-Host "MCP:     $McpUrl" -ForegroundColor Cyan
Write-Host "Health:  $HealthUrl" -ForegroundColor Cyan
Write-Host "OAuth:   $OAuthUrl" -ForegroundColor Cyan
Write-Host 'Webhook: http://127.0.0.1:8765/oura-webhook' -ForegroundColor Cyan

if (-not $s.authorized) {
    Write-Host 'Oura authorization required. Opening browser...' -ForegroundColor Yellow
    Start-Process $OAuthUrl
} else {
    Write-Host 'Oura is authorized; existing tokens will be reused/refreshed.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Connect cptr/Open WebUI to:' -ForegroundColor Magenta
Write-Host $McpUrl -ForegroundColor White
Write-Host ''
Write-Host 'Commands:' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1              Start everything' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Setup       Re-run setup/configuration' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Update      Pull latest GitHub code/dependencies' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Status      Check service/Oura status' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Stop        Stop the local service' -ForegroundColor DarkCyan
