# Personal Health MCP

A local-first MCP server for connecting personal health data to AI assistants. Oura is the primary personal-data integration, with analytics and medical/reference integrations designed for extensibility.

The project is intended for personal analytics and research. Private credentials, OAuth tokens, and personal health records are stored locally by default.

## Highlights

- Oura API V2 OAuth 2.0
- Automatic token refresh
- Paginated Oura collection access
- Local health history and analytics
- Personal baselines, trends, anomalies, correlations, sleep debt, and regularity analysis
- Compact health snapshots designed for smaller local AI models
- Medical/reference integrations including PubMed/NCBI, MedlinePlus, ICD terminology, LOINC, RxTerms, NPI, CMS, and FDA/openFDA where supported
- MCP Streamable HTTP
- Configurable bind address and port
- One PowerShell launcher for setup, start, update, status, diagnostics, and stop
- Automatic Python/Git installation through Windows Package Manager when available
- Optional webhook architecture

## Windows quick start

1. Clone or download this repository.
2. Open PowerShell in the repository directory.
3. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-health.ps1
```

The launcher checks prerequisites, can install Git and Python automatically through `winget`, creates a virtual environment, installs dependencies, creates local configuration, starts the MCP server, and opens Oura OAuth when needed.

### Daily commands

```powershell
.\start-health.ps1              # Start
.\start-health.ps1 -Setup       # Configure again
.\start-health.ps1 -Update      # Update code/dependencies
.\start-health.ps1 -Status      # Check status
.\start-health.ps1 -Doctor      # Diagnose installation
.\start-health.ps1 -Stop        # Stop
```

The launcher is location-independent and does not assume `C:\AI` or another fixed path. The MCP URL is copied to the clipboard when the service starts.

## Configuration

The launcher creates `oura.env` automatically. The example contains:

```env
OURA_CLIENT_ID=PASTE_YOUR_OURA_CLIENT_ID_HERE
OURA_CLIENT_SECRET=PASTE_YOUR_OURA_CLIENT_SECRET_HERE
OURA_REDIRECT_URI=http://127.0.0.1:8765/oauth/callback
OURA_SCOPES=email personal daily heartrate workout tag session spo2Daily
OURA_HOST=127.0.0.1
OURA_PORT=8765
OURA_TOKEN_FILE=data/tokens.json
```

Change `OURA_PORT` to an unused local port if needed. The launcher uses the configured port for the MCP service and health checks. The Oura Redirect URI must exactly match an allowed URI in your Oura developer application.

Keep `OURA_HOST=127.0.0.1` for normal personal use. Port 8000 is not used or reserved by this project.

Optional NCBI configuration:

```env
NCBI_EMAIL=you@example.com
NCBI_API_KEY=your_key
```

An NCBI API key is optional.

## Oura setup

Create an Oura API application and add the exact local callback shown in `oura.env`. On first start, the launcher opens the browser authorization flow automatically. Tokens are stored locally and excluded from Git.

## MCP endpoint

Default MCP endpoint:

```text
http://127.0.0.1:8765/mcp
```

Default health endpoint:

```text
http://127.0.0.1:8765/health
```

Use the configured host and port if changed.

## Architecture

```text
Oura Cloud
   |
   | OAuth / API V2
   v
Local Personal Health MCP
   |
   +--> local state/database
   +--> analytics
   +--> medical/reference APIs
   |
   | MCP Streamable HTTP
   v
cptr / Open WebUI / other MCP clients
   |
   v
Local or remote AI model
```

## Analytics

The analytics layer is intended to turn raw health measurements into model-friendly information. It can support personal baselines, rolling trends, anomaly detection, period comparisons, correlations, tag/condition comparisons, sleep debt, sleep regularity, and longitudinal summaries.

## Medical/reference integrations

Public reference integrations can include PubMed/NCBI, MedlinePlus, ICD-10/ICD-11 terminology, LOINC, RxTerms, NPI Registry, CMS Coverage, and FDA/openFDA. These sources are external services and their own terms and availability apply.

## Webhooks

Webhooks are optional. The local service works without public ingress. If enabled, Oura Cloud needs a public HTTPS endpoint. Use a secure tunnel/reverse proxy and expose only the intended webhook route; do not expose the MCP endpoint directly to the Internet.

See `WEBHOOKS.md` for the planned deployment architecture.

## Privacy and security

This is a local-first application and does not provide a central project-hosted health-data service. Do not commit credentials, OAuth tokens, databases, or personal health data.

Read `PRIVACY.md` for data-flow information and `TERMS.md` for software terms and the medical-use disclaimer. `SECURITY.md` contains additional credential and network guidance.

## Documentation

- `CONFIGURATION.md` — configuration reference
- `INSTALLATION.md` — installation and troubleshooting
- `MCP_TOOLS.md` — MCP tools/resources
- `INTEGRATIONS.md` — health and medical integrations
- `WEBHOOKS.md` — optional webhook deployment
- `SECURITY.md` — security guidance
- `PRIVACY.md` — privacy and data-flow information
- `TERMS.md` — terms and disclaimer
- `DEVELOPMENT.md` — development notes

## License and third parties

See the repository license file if present. Third-party APIs, datasets, libraries, and services remain subject to their own licenses, terms, attribution requirements, and usage limits.
