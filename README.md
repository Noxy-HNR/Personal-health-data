# Personal Health MCP

A local-first MCP server for connecting personal health data to AI assistants. Oura is the primary personal-data integration, with local analytics and public medical/reference sources alongside it.

## Quick start — Windows

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-health.ps1
```

The launcher is the only script most users normally need. It can install missing prerequisites, create the virtual environment, install dependencies, create configuration, guide Oura setup, start the service, and diagnose problems.

Useful commands:

```powershell
.\start-health.ps1
.\start-health.ps1 -Setup
.\start-health.ps1 -Update
.\start-health.ps1 -Status
.\start-health.ps1 -Doctor
.\start-health.ps1 -Stop
```

## Features

- Oura API V2 OAuth 2.0 integration and token refresh
- Read-only Oura data access with pagination and bounded time-series queries
- Local SQLite health history/state
- Personal baselines, rolling trends, anomalies, correlations, period comparisons, sleep debt and sleep regularity
- Compact health snapshots designed for AI context efficiency
- Public medical/reference integrations such as PubMed/NCBI, MedlinePlus, ICD terminology, LOINC, RxTerms, NPI, CMS Coverage and FDA/openFDA where supported
- MCP Streamable HTTP
- Configurable local host/port
- Optional Oura webhooks for deployments with public HTTPS ingress
- Single Windows launcher for setup, update, status, diagnostics and stop

## Configuration

The launcher creates `oura.env` automatically from `oura.env.example` when needed.

```env
OURA_CLIENT_ID=
OURA_CLIENT_SECRET=
OURA_REDIRECT_URI=http://127.0.0.1:8765/oauth/callback
OURA_SCOPES=email personal daily heartrate workout tag session spo2Daily
OURA_HOST=127.0.0.1
OURA_PORT=8765
OURA_TOKEN_FILE=data/tokens.json

# Optional NCBI settings
# NCBI_EMAIL=you@example.com
# NCBI_API_KEY=
```

Keep `OURA_HOST=127.0.0.1` for local-only operation. Change `OURA_PORT` if the default is occupied. If you change the port, also change `OURA_REDIRECT_URI` and the matching Oura application callback. Port 8000 is not used by this project.

## MCP endpoint

Default endpoint: `http://127.0.0.1:8765/mcp`

Default health check: `http://127.0.0.1:8765/health`

Use the configured host and port if changed.

## Oura setup

Create an Oura API application and add the exact local redirect URI shown in `oura.env`. On first launch, the launcher guides you through authorization and stores OAuth tokens locally. Never commit credentials, tokens, databases or personal health data.

## Analytics

The analytics layer performs calculations locally so AI models receive useful derived information rather than large raw datasets. It supports personal baselines, trends, anomaly detection, correlations, tagged-condition comparisons, sleep debt, sleep regularity and longitudinal analysis.

## Medical/reference data

External medical/reference sources are queried on demand and are not stored as a replacement for personal records. PubMed/NCBI can optionally use an API key for higher request limits. External sources remain subject to their own terms and licenses.

## Webhooks

Webhooks are optional. The local system works without them. If enabled, Oura Cloud requires a publicly reachable HTTPS endpoint. Use a secure tunnel or reverse proxy and expose only the webhook route; do not expose the MCP endpoint directly to the Internet.

## Repository layout

The project intentionally keeps user-facing documentation compact while retaining separate code modules where that improves maintainability.

- `start-health.ps1` — installer, configurator, launcher and diagnostics
- `health_mcp.py` — MCP service entry point
- `oura_service.py` — Oura API/authentication layer
- `analytics.py` / `analytics_tools.py` — local analytics
- `medical_tools.py` and source-specific modules — public reference integrations
- `oura.env.example` — safe configuration template
- `PRIVACY.md` — privacy policy
- `TERMS.md` — terms of use
- `SECURITY.md` — security guidance

Runtime files such as `.venv`, `oura.env`, tokens and local databases are excluded from Git.

## Privacy and medical disclaimer

This software is designed to keep personal credentials, tokens, databases and health records on the user's computer by default. It does not provide medical diagnosis or treatment. AI-generated analysis is informational and should not be treated as professional medical advice.

See `PRIVACY.md`, `TERMS.md`, and `SECURITY.md` for the full policies.

## Development

Developers can use the same launcher with `-Setup`, `-Update` and `-Doctor`. Python modules are intentionally kept separate where that improves maintainability.

## License

See the repository license. Oura, NCBI, FDA and other external services remain subject to their respective terms and agreements.
