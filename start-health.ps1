$ErrorActionPreference='Stop'
$RepoUrl='https://github.com/Noxy-HNR/Personal-health-data.git'
$Root='C:\AI\Personal-health-data'; $Venv=Join-Path $Root '.venv'; $Py=Join-Path $Venv 'Scripts\python.exe'; $EnvFile=Join-Path $Root 'oura.env'; $Example=Join-Path $Root 'oura.env.example'; $Service=Join-Path $Root 'health_mcp_full.py'
Write-Host '=== Personal Health MCP ===' -ForegroundColor Cyan
if(-not(Test-Path(Join-Path $Root '.git'))){ New-Item -ItemType Directory -Force -Path (Split-Path $Root)|Out-Null; git clone $RepoUrl $Root } else { git -C $Root pull --ff-only }
if(-not(Test-Path $EnvFile)){ Copy-Item $Example $EnvFile; Write-Host "Created $EnvFile - enter Oura Client ID and Client Secret, then save it." -ForegroundColor Yellow; Start-Process notepad.exe -ArgumentList $EnvFile; do{Start-Sleep 2;$t=Get-Content $EnvFile -Raw}until(($t-match 'OURA_CLIENT_ID=(?!PASTE_YOUR_OURA_CLIENT_ID_HERE).+') -and ($t-match 'OURA_CLIENT_SECRET=(?!PASTE_YOUR_OURA_CLIENT_SECRET_HERE).+')) }
if(-not(Test-Path $Py)){ python -m venv $Venv }
& $Py -m pip install -r (Join-Path $Root 'requirements.txt') --disable-pip-version-check
Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',"Set-Location '$Root'; & '$Py' '$Service'")
for($i=0;$i-lt30;$i++){Start-Sleep 1;try{$s=Invoke-RestMethod 'http://127.0.0.1:8765/health';if($s.status-eq'ok'){break}}catch{}}
try{$s=Invoke-RestMethod 'http://127.0.0.1:8765/health'}catch{Write-Host 'Service failed to start. Check the Python window.' -ForegroundColor Red;exit 1}
Write-Host 'Service running on http://127.0.0.1:8765' -ForegroundColor Green
Write-Host 'MCP:     http://127.0.0.1:8765/mcp'
Write-Host 'OAuth:   http://127.0.0.1:8765/oauth/start'
Write-Host 'Webhook: http://127.0.0.1:8765/oura-webhook'
if(-not $s.authorized){Start-Process 'http://127.0.0.1:8765/oauth/start'}
Write-Host 'Connect cptr to http://127.0.0.1:8765/mcp' -ForegroundColor Magenta
