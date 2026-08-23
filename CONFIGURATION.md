# Configuration

The normal configuration file is `oura.env`. The unified `start-health.ps1` launcher creates it automatically on first run and guides you through setup.

## Server

```env
OURA_HOST=127.0.0.1
OURA_PORT=8765
```

`OURA_PORT` may be changed to any unused local TCP port. The launcher uses the configured port for health checks and displayed MCP URLs. If the Oura OAuth redirect URI uses the local port, it must exactly match an allowed URI in the Oura developer application.

## Oura OAuth

```env
OURA_CLIENT_ID=...
OURA_CLIENT_SECRET=...
OURA_REDIRECT_URI=http://127.0.0.1:8765/oauth/callback
OURA_SCOPES=email personal daily heartrate workout tag session spo2Daily
```

The redirect URI must exactly match an allowed URI in the Oura developer application.

## Local data

```env
OURA_TOKEN_FILE=data/tokens.json
```

OAuth tokens and local personal-health data are runtime state and must not be committed to Git.

## Optional NCBI

```env
NCBI_EMAIL=you@example.com
NCBI_API_KEY=
```

An NCBI key is optional.

## Launcher modes

```powershell
.\start-health.ps1
.\start-health.ps1 -Setup
.\start-health.ps1 -Update
.\start-health.ps1 -Status
.\start-health.ps1 -Doctor
.\start-health.ps1 -Stop
```

`-Doctor` performs a deeper diagnostic of Python, dependencies, configuration, database, Oura connectivity, port availability, and the MCP endpoint.

## Environment portability

Do not put machine-specific absolute paths in configuration. The launcher resolves the repository directory automatically, so the project can live under any user-selected directory.
