[CmdletBinding()]
param(
    [ValidateSet('Start','Setup','Update','Stop','Status','Doctor')]
    [string]$Mode = 'Start'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$EnvFile = Join-Path $Root 'oura.env'
$Example = Join-Path $Root 'oura.env.example'
$Requirements = Join-Path $Root 'requirements.txt'
$Service = Join-Path $Root 'health_mcp.py'
$DataDir = Join-Path $Root 'data'
$LogFile = Join-Path $DataDir 'server.log'
$ErrorLogFile = Join-Path $DataDir 'server-error.log'
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
    if (-not (Test-Path (Join-Path $Root '.git'))) {
        throw "This launcher must be run from a cloned Personal Health MCP repository. Missing Git repository at $Root"
    }
    if ($Mode -in @('Start','Setup','Update')) {
        Write-Host 'Checking for application updates...' -ForegroundColor Yellow
        git -C $Root pull --ff-only | Out-Host
    }
}

function Edit-Config {
    if (-not (Test-Path $EnvFile)) { Copy-Item $Example $EnvFile }
    Load-ServerConfig
    Write-Host ''
    Write-Host 'Configuration' -ForegroundColor Cyan
    Write-Host '-------------' -ForegroundColor Cyan
    Write-Host "Current host: $HostAddress"
    Write-Host "Current port: $Port"
    $changePort = Read-Host 'Change the server port? [y/N]'
    if ($changePort -match '^[Yy]') {
        do {
            $newPort = Read-Host 'Enter an unused local TCP port (1024-65535)'
            $portNumber = 0
            $ok = [int]::TryParse($newPort, [ref]$portNumber)
            if (-not $ok -or $portNumber -lt 1024 -or $portNumber -gt 65535) {
                Write-Host 'Enter a number from 1024 to 65535.' -ForegroundColor Red
                $ok = $false
            }
        } while (-not $ok)
        $text = Get-Content $EnvFile -Raw
        if ($text -match '(?m)^OURA_PORT=.*$') { $text = [regex]::Replace($text,'(?m)^OURA_PORT=.*$',"OURA_PORT=$portNumber") }
        else { $text += "`nOURA_PORT=$portNumber`n" }
        $redirect = "http://127.0.0.1:$portNumber/oauth/callback"
        if ($text -match '(?m)^OURA_REDIRECT_URI=.*$') { $text = [regex]::Replace($text,'(?m)^OURA_REDIRECT_URI=.*$',"OURA_REDIRECT_URI=$redirect") }
        Set-Content -Path $EnvFile -Value $text -Encoding UTF8
        Load-ServerConfig
    }

    $text = Get-Content $EnvFile -Raw
    $missing = ($text -match 'PASTE_YOUR_OURA_CLIENT_ID_HERE') -or ($text -match 'PASTE_YOUR_OURA_CLIENT_SECRET_HERE') -or ($text -notmatch '(?m)^OURA_CLIENT_ID=.+') -or ($text -notmatch '(?m)^OURA_CLIENT_SECRET=.+')
    if ($missing) {
        Write-Host ''
        Write-Host 'Oura credentials are required for Oura integration.' -ForegroundColor Yellow
        Write-Host 'The secret is stored locally and is not printed by this launcher.' -ForegroundColor DarkYellow
        Start-Process notepad.exe -ArgumentList $EnvFile -Wait
    }
    $text = Get-Content $EnvFile -Raw
    $missing = ($text -match 'PASTE_YOUR_OURA_CLIENT_ID_HERE') -or ($text -match 'PASTE_YOUR_OURA_CLIENT_SECRET_HERE') -or ($text -notmatch '(?m)^OURA_CLIENT_ID=.+') -or ($text -notmatch '(?m)^OURA_CLIENT_SECRET=.+')
    if ($missing) { throw 'Oura credentials were not configured. Run -Setup when you are ready.' }
    try { icacls $EnvFile /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null } catch { Write-Host 'Could not tighten credential-file ACL; continuing.' -ForegroundColor DarkYellow }
    Load-ServerConfig
}

function Ensure-Config {
    if (-not (Test-Path $Example)) { throw "Missing configuration template: $Example" }
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $Example $EnvFile
        Write-Host "Created local configuration: $EnvFile" -ForegroundColor Green
    }
    Load-ServerConfig
    $text = Get-Content $EnvFile -Raw
    $missing = ($text -match 'PASTE_YOUR_OURA_CLIENT_ID_HERE') -or ($text -match 'PASTE_YOUR_OURA_CLIENT_SECRET_HERE') -or ($text -notmatch '(?m)^OURA_CLIENT_ID=.+') -or ($text -notmatch '(?m)^OURA_CLIENT_SECRET=.+')
    if ($missing) { Edit-Config }
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
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'),$Port)
        $listener.Start(); $listener.Stop(); return $true
    } catch { return $false }
}

function Stop-HealthService {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$Service*" }
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host 'Personal Health MCP stopped.' -ForegroundColor Green
}

function Run-Doctor {
    Write-Header 'Doctor'
    Load-ServerConfig
    $checks = @()
    $checks += [pscustomobject]@{Name='Git'; Ok=(Test-Command 'git'); Detail='Git executable'}
    $checks += [pscustomobject]@{Name='Python'; Ok=((Test-Command 'python') -or (Test-Path $Py)); Detail='Python 3 / virtual environment'}
    $checks += [pscustomobject]@{Name='Repository'; Ok=(Test-Path (Join-Path $Root '.git')); Detail=$Root}
    $checks += [pscustomobject]@{Name='Configuration'; Ok=(Test-Path $EnvFile); Detail=$EnvFile}
    $checks += [pscustomobject]@{Name='Requirements'; Ok=(Test-Path $Requirements); Detail='requirements.txt'}
    $checks += [pscustomobject]@{Name='Data directory'; Ok=(Test-Path $DataDir); Detail='data/'}
    $health = Get-Health
    $checks += [pscustomobject]@{Name='MCP service'; Ok=($null -ne $health); Detail=$(if($health){'Running'}else{'Not running'})}
    $portOk = Test-PortAvailable
    $checks += [pscustomobject]@{Name='Configured port'; Ok=($portOk -or $null -ne $health); Detail="$HostAddress`:$Port"}
    $logOk = Test-Path $LogFile
    $checks += [pscustomobject]@{Name='Startup log'; Ok=$logOk; Detail=$LogFile}
    foreach ($c in $checks) {
        if ($c.Ok) { Write-Host ("[OK] {0,-22} {1}" -f $c.Name,$c.Detail) -ForegroundColor Green }
        else { Write-Host ("[!!] {0,-22} {1}" -f $c.Name,$c.Detail) -ForegroundColor Red }
    }
    if ($health) {
        $authColor = if ($health.authorized) { 'Green' } else { 'Yellow' }
        Write-Host ("[OK] Oura authorization    {0}" -f $health.authorized) -ForegroundColor $authColor
        Write-Host "MCP:    http://$HostAddress`:$Port/mcp" -ForegroundColor Cyan
        Write-Host "Health: http://$HostAddress`:$Port/health" -ForegroundColor Cyan
    }
    Write-Host ''
    Write-Host 'Doctor complete. Credentials and tokens are never printed.' -ForegroundColor Cyan
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
    Write-Host "MCP: http://$HostAddress`:$Port/mcp" -ForegroundColor Cyan
    exit 0
}

Ensure-PythonEnv
$HealthUrl = "http://$HostAddress`:$Port/health"
$McpUrl = "http://$HostAddress`:$Port/mcp"
$OAuthUrl = "http://$HostAddress`:$Port/oauth/start"

if ($Mode -eq 'Status') {
    $s = Get-Health
    if ($null -eq $s) {
        Write-Host "Service: STOPPED / unreachable ($HealthUrl)" -ForegroundColor Red
        if (Test-Path $LogFile) {
            Write-Host ''
            Write-Host 'Recent server log:' -ForegroundColor Yellow
            Get-Content $LogFile -Tail 30 | Out-Host
        }
        if (Test-Path $ErrorLogFile) {
            Write-Host ''
            Write-Host 'Recent server errors:' -ForegroundColor Red
            Get-Content $ErrorLogFile -Tail 30 | Out-Host
        }
        exit 1
    }
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

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
if (Test-Path $LogFile) { Remove-Item $LogFile -Force -ErrorAction SilentlyContinue }
if (Test-Path $ErrorLogFile) { Remove-Item $ErrorLogFile -Force -ErrorAction SilentlyContinue }
Write-Host "Starting Personal Health MCP on $HostAddress`:$Port..." -ForegroundColor Green

$process = Start-Process -FilePath $Py -ArgumentList @($Service) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -PassThru

$healthy = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) { break }
    $s = Get-Health
    if ($null -ne $s -and $s.status -eq 'ok') { $healthy = $true; break }
}
if (-not $healthy) {
    Write-Host 'Service did not become healthy within 45 seconds.' -ForegroundColor Red
    if ($process.HasExited) {
        Write-Host "Python exited with code $($process.ExitCode)." -ForegroundColor Red
    }
    if (Test-Path $LogFile) {
        Write-Host ''
        Write-Host 'Server output:' -ForegroundColor Yellow
        Get-Content $LogFile -Tail 60 | Out-Host
    }
    if (Test-Path $ErrorLogFile) {
        Write-Host ''
        Write-Host 'Server errors:' -ForegroundColor Red
        Get-Content $ErrorLogFile -Tail 60 | Out-Host
    }
    Write-Host ''
    Write-Host 'Run .\start-health.ps1 -Doctor for diagnostics.' -ForegroundColor Yellow
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
