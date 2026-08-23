# Installation

## Requirements

Windows users need:

- Windows 10/11
- Git for Windows
- Python 3.11+ recommended
- An Oura API application if Oura data is desired

The launcher creates the Python virtual environment and installs project dependencies automatically.

## Install

Clone the repository, open PowerShell in the repository directory, then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-health.ps1
```

On first run the launcher creates `oura.env` and opens it in Notepad. Enter the Oura client ID and secret, save, and close Notepad. The launcher then starts the service and opens the OAuth authorization page if needed.

## Existing installation

Start:

```powershell
.\start-health.ps1
```

Update:

```powershell
.\start-health.ps1 -Update
```

Status:

```powershell
.\start-health.ps1 -Status
```

Stop:

```powershell
.\start-health.ps1 -Stop
```

## Changing ports

Edit `OURA_PORT` in `oura.env`, then update `OURA_REDIRECT_URI` to the same port. Register the new redirect URI in the Oura application. Restart the service.

## Troubleshooting

### Service does not start

Run:

```powershell
.\start-health.ps1 -Status
```

Then run the server manually from the repository virtual environment to see Python errors:

```powershell
.\.venv\Scripts\python.exe .\health_mcp.py
```

### Port already in use

Choose another value for `OURA_PORT`. The project does not require port 8000.

### OAuth redirect error

The callback in `oura.env` must exactly match the Redirect URI registered in the Oura developer application, including scheme, host, port, and path.

### Credentials repeatedly requested

Verify that `oura.env` contains real values rather than the placeholders from `oura.env.example`. Existing tokens are stored under `data/`.

### cptr cannot connect

Confirm the MCP service is running and use the printed MCP endpoint. The default is:

`http://127.0.0.1:8765/mcp`

If you changed the port, use the configured port.
