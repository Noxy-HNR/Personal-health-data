[CmdletBinding()]
param(
    [ValidateSet('Start','Setup','Update','Stop','Status','Doctor')]
    [string]$Mode = 'Start'
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/Noxy-HNR/Personal-health-data.git'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$EnvFile = Join-Path $Root 'oura.env'
$Example = Join-Path $Root 'oura.env.example'
$Requirements = Join-Path $Root 'requirements.txt'
$Service = Join-Path $Root 'health_mcp.py'
$Port = 8765
$HostAddress = '127.0.0.1'

function Write-Header($text) {
    Write-Host ''
    Write-Host '================================================' -ForegroundColor Cyan
    Write-Host "  Personal Health MCP - $text" -ForegroundColor Cyan
    Write-Host '================================================' -ForegroundColor Cyan
    Write-Host ''
}

function Test-Command($name) { return $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

function Install-Prerequisite($name, $wingetId) {
    if (Test-Command $name) { return $true }
    if (Test-Command 'winget') {
        Write-Host "$name was not found. Installing $name with winget..." -ForegroundColor Yellow
        winget install --id $wingetId --exact --accept-source-agreements --accept-package-agreements
        return (Test-Command $name)
    }
    return $false
}

function Load-ServerConfig {
    $script:Port = 8765
    $script:HostAddress = '127.0.0.1'
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
                $name = $Matches[1]
                $value = $Matches[2].Trim().Trim('"').Trim("'")
                if ($name -eq 'OURA_PORT' -and $value -match '^\d+$') { $script:Port = [int]$value }
                if ($name -eq 'OURA_HOST' -and $value) { $script:HostAddress = $value }
            }
        }
    }
}

function Ensure-Tools {
    if (-not (Test-Command 'git')) {
        if (-not (Install-Prerequisite 'git' 'Git.Git')) { throw 'Git is required and could not be installed automatically.' }
    }
    if (-not (Test-Command 'python') -and -not (Test-Path $Py)) {
        if (-not (Install-Prerequisite 'python' 'Python.Python.3.12')) { throw 'Python 3 is required and could not be installed automatically.' }
    }
}

function Ensure-Repo {
    # The launcher is intended to live inside the repository. If it is run from a
    # copied folder, update that checkout rather than creating nested repositories.
    if (-not (Test-Path (Join-Path $Root '.git'))) {
        Write-Host 'This launcher is not inside a Git checkout.' -ForegroundColor Yellow
        Write-Host 'The repository should be cloned/downloaded before running it.' -ForegroundColor Yellow
        throw "Missing Git repository at $Root"
    }
    if ($Mode -in @('Start','Setup','Update')) {
        Write-Host 'Checking for application updates...' -ForegroundColor Yellow
        git -C $Root pull --ff-only | Out-Host
    }
}

function Ensure-Config {
    if (-not (Test-Path $Example)) { throw "Missing configuration template: $Example" }
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $Example $EnvFile
        Write-Host "Created local configuration: $EnvFile" -ForegroundColor Green
        Write-Host 'Opening the configuration wizard...' -ForegroundColor Yellow
        Edit-Config
    }
    Load-ServerConfig
}

function Edit-Config {
    if (-not (Test-Path $EnvFile)) { Copy-Item $Example $EnvFile }
    Write-Host ''
    Write-Host 'Configuration' -ForegroundColor Cyan
    Write-Host '-------------' -ForegroundColor Cyan
    Write-Host "Current host: $HostAddress"
    Write-Host "Current port: $Port"
    $changePort = Read-Host 'Change the server port? [y/N]'
    if ($changePort -match '^[Yy]') {
        do {
            $newPort = Read-Host 'Enter an unused local TCP port'
            $ok = [int]::TryParse($newPort, [ref]$null)
            if (-not $ok -or [int]$newPort -lt 1024 -or [int]$newPort -gt 65535) { Write-Host 'Enter a number from 1024 to 65535.' -ForegroundColor Red; $ok = $false }
        } while (-not $ok)
        $text = Get-Content $EnvFile -Raw
        if ($text -match '(?m)^OURA_PORT=.*$') { $text = [regex]::Replace($text,'(?m)^OURA_PORT=.*$',"OURA_PORT=$newPort") }
        else { $text += "`nOURA_PORT=$newPort`n" }
        $redirect = "http://127.0.0.1:$newPort/oauth/callback"
        if ($text -match '(?m)^OURA_REDIRECT_URI=.*$') { $text = [regex]::Replace($text,'(?m)^OURA_REDIRECT_URI=.*$',"OURA_REDIRECT_URI=$redirect") }
        Set-Content -Path $EnvFile -Value $text -Encoding UTF8
        Load-ServerConfig
    }

    $text = Get-Content $EnvFile -Raw
    $missing = ($text -match 'PASTE_YOUR_OURA_CLIENT_ID_HERE') -or ($text -match 'PASTE_YOUR_OURA_CLIENT_SECRET_HERE') -or ($text -notmatch '(?m)^OURA_CLIENT_ID=.+') -or ($text -notmatch '(?m)^OURA_CLIENT_SECRET=.+')
    if ($missing) {
        Write-Host ''
        Write-Host 'Oura credentials are required for Oura integration.' -ForegroundColor Yellow
        Write-Host 'The secret will not be displayed by this launcher.' -ForegroundColor DarkYellow
        Start-Process notepad.exe -ArgumentList $EnvFile -Wait
    }

    $text = Get-Content $EnvFile -Raw
    $missing = ($text -match 'PASTE_YOUR_OURA_CLIENT_ID_HERE') -or ($text -match 'PASTE_YOUR_OURA_CLIENT_SECRET_HERE') -or ($text -notmatch '(?m)^OURA_CLIENT_ID=.+') -or ($text -notmatch '(?m)^OURA_CLIENT_SECRET=.+')
    if ($missing) { throw 'Oura credentials are not configured. Run -Setup when you are ready.' }
    try { icacls $EnvFile /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null } catch { Write-Host 'Could not tighten credential-file ACL; continuing.' -ForegroundColor DarkYellow }
    Load-ServerConfig
}

function Ensure-PythonEnv {
    if (-not (Test-Path $Py)) {
        Write-Host 'Creating Python virtual environment...' -ForegroundColor Yellow
        if (Test-Command 'python') { python -m venv $Venv }
        else { throw 'Python executable was not found after installation.' }
    }
    Write-Host 'Installing/updating dependencies...' -ForegroundColor Yellow
    & $Py -m pip install --upgrade pip --disable-pip-version-check | Out-Host
    & $Py -m pip install -r $Requirements --disable-pip-version-check | Out-Host
}

function Get-Health {
    try { return Invoke-RestMethod -Uri "http://$HostAddress`:$Port/health" -TimeoutSec 3 } catch { return $null }
}

function Test-PortAvailable {
    try { $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'),$Port); $listener.Start(); $listener.Stop(); return $true } catch { return $false }
}

function Stop-HealthService {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$Service*" }
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host 'Personal Health MCP stopped.' -ForegroundColor Green
}

function Copy-McpUrl {
    $url = "http://$HostAddress`:$Port/mcp"
    try { Set-Clipboard -Value $url; Write-Host 'MCP URL copied to clipboard.' -ForegroundColor Green } catch { Write-Host $url -ForegroundColor White }
}

function Run-Doctor {
    Write-Header 'Doctor'
    $checks = @()
    $checks += [pscustomobject]@{Name='Git'; Ok=(Test-Command 'git'); Detail='Git executable'}
    $checks += [pscustomobject]@{Name='Python'; Ok=((Test-Command 'python') -or (Test-Path $Py)); Detail='Python 3 / virtual environment'}
    $checks += [pscustomobject]@{Name='Repository'; Ok=(Test-Path (Join-Path $Root '.git')); Detail=$Root}
    $checks += [pscustomobject]@{Name='Configuration'; Ok=(Test-Path $EnvFile); Detail=$EnvFile}
    $checks += [pscustomobject]@{Name='Requirements'; Ok=(Test-Path $Requirements); Detail='requirements.txt'}
    $checks += [pscustomobject]@{Name='Database directory'; Ok=(Test-Path (Join-Path $Root 'data')); Detail='data/'}
    Load-ServerConfig
    $checks += [pscustomobject]@{Name='Port'; Ok=(Test-PortAvailable -or ($null -ne (Get-Health))); Detail="$HostAddress`:$Port"}
    $health = Get-Health
    $checks += [pscustomobject]@{Name='MCP service'; Ok=($null -ne $health); Detail=(if($health){'Running'}else{'Not running'})}
    foreach ($c in $checks) {
        if ($c.Ok) { Write-Host ("[OK] {0,-22} {1}" -f $c.Name,$c.Detail) -ForegroundColor Green }
        else { Write-Host ("[!!] {0,-22} {1}" -f $c.Name,$c.Detail) -ForegroundColor Red }
    }
    if ($health) {
        Write-Host ("[OK] Oura authorization      {0}" -f $health.authorized) -ForegroundColor $(if($health.authorized){'Green'}else{'Yellow'})
        Write-Host "MCP:    http://$HostAddress`:$Port/mcp" -ForegroundColor Cyan
        Write-Host "Health: http://$HostAddress`:$Port/health" -ForegroundColor Cyan
    }
    Write-Host ''
    Write-Host 'Doctor complete. No credentials are printed.' -ForegroundColor Cyan
}

if (-not (Test-Path $Root)) { throw "Installation directory does not exist: $Root" }

Write-Header $Mode

if ($Mode -eq 'Stop') { Load-ServerConfig; Stop-HealthService; exit 0 }
if ($Mode -eq 'Doctor') { Run-Doctor; exit 0 }

Ensure-Tools
Ensure-Repo
Ensure-Config
Load-ServerConfig

if ($Mode -eq 'Setup') {
    Edit-Config
    Ensure-PythonEnv
    Write-Host ''
    Write-Host 'Setup complete.' -ForegroundColor Green
    Write-Host "MCP will use http://$HostAddress`:$Port/mcp" -ForegroundColor Cyan
    exit 0
}

Ensure-PythonEnv

$HealthUrl = "http://$HostAddress`:$Port/health"
$McpUrl = "http://$HostAddress`:$Port/mcp"
$OAuthUrl = "http://$HostAddress`:$Port/oauth/start"

if ($Mode -eq 'Status') {
    $s = Get-Health
    if ($null -eq $s) { Write-Host "Service: STOPPED / unreachable ($HealthUrl)" -ForegroundColor Red; exit 1 }
    Write-Host 'Service:    RUNNING' -ForegroundColor Green
    Write-Host "MCP:        $McpUrl" -ForegroundColor Cyan
    Write-Host "Authorized: $($s.authorized)" -ForegroundColor Cyan
    Write-Host "Host:       $HostAddress" -ForegroundColor Cyan
    Write-Host "Port:       $Port" -ForegroundColor Cyan
    exit 0
}

if ($Mode -eq 'Update') {
    Write-Host 'Update complete. Service was not restarted.' -ForegroundColor Green
    exit 0
}

$current = Get-Health
if ($null -ne $current) {
    Write-Host "Personal Health MCP is already running on $HostAddress`:$Port." -ForegroundColor Green
    if (-not $current.authorized) { Start-Process $OAuthUrl }
    exit 0
}

if (-not (Test-PortAvailable)) { throw "Port $Port is already in use. Change OURA_PORT in oura.env or use -Setup." }

Write-Host "Starting Personal Health MCP on $HostAddress`:$Port..." -ForegroundColor Green
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
    Write-Host "Run .\start-health.ps1 -Doctor for diagnostics." -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host 'Personal Health MCP is running.' -ForegroundColor Green
Write-Host "MCP:     $McpUrl" -ForegroundColor Cyan
Write-Host "Health:  $HealthUrl" -ForegroundColor Cyan
Write-Host "OAuth:   $OAuthUrl" -ForegroundColor Cyan
Write-Host "Webhook: $HostAddress`:$Port/oura-webhook (public HTTPS required for Oura Cloud)" -ForegroundColor Cyan
try { Set-Clipboard -Value $McpUrl; Write-Host 'MCP URL copied to clipboard.' -ForegroundColor Green } catch {}

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
Write-Host '  .\start-health.ps1 -Setup       Configuration wizard' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Update      Update code/dependencies' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Status      Check service/Oura status' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Doctor      Diagnose installation' -ForegroundColor DarkCyan
Write-Host '  .\start-health.ps1 -Stop        Stop the local service' -ForegroundColor DarkCyan
