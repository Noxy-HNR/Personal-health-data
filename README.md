# Personal Health MCP

A local-first MCP server for connecting personal health data to AI assistants. The project is designed to work with Oura Ring data today, while keeping the architecture extensible for additional health and medical-reference integrations.

The service is intended for personal analytics and research. It keeps private credentials, OAuth tokens, and personal health records on the user's machine.

## Features

- Oura API V2 OAuth 2.0 integration
- Automatic token refresh
- Read-only Oura data access
- Automatic Oura pagination
- Bounded time-series queries
- Compact health snapshots for AI models
- Personal health analytics and trend tools
- Local medical/reference integrations
- MCP Streamable HTTP
- Configurable bind address and port
- Single PowerShell launcher for setup, start, update, status, and stop
- Local credential/token storage excluded from Git
- Optional webhook architecture for deployments with public HTTPS ingress

## Architecture

```text
Oura Cloud
    |
    | OAuth 2.0 / API V2
    v
Local Personal Health MCP
    |
    +--> SQLite / local state
    |
    +--> Analytics
    |
    +--> Medical/reference APIs
    |
    | MCP Streamable HTTP
    v
cptr / Open WebUI / other MCP clients
    |
    v
Local or remote AI model
```

By default the service binds to `127.0.0.1:8765`. Port 8000 is not reserved by this project and can be used by another local service such as llama.cpp.

## Windows quick start

Clone the repository, open PowerShell in the repository directory, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-health.ps1
```

The launcher automatically:

1. Checks the local installation.
2. Creates a Python virtual environment.
3. Installs dependencies.
4. Creates `oura.env` from the example configuration when needed.
5. Opens the configuration file so you can enter your Oura credentials.
6. Starts the MCP server.
7. Checks the health endpoint.
8. Opens Oura OAuth when authorization is required.
9. Prints the MCP endpoint for your client.

If configuration and OAuth tokens already exist, they are reused.

## Configuration

All normal server configuration is in `oura.env`.

```env
OURA_CLIENT_ID=...
OURA_CLIENT_SECRET=...
OURA_REDIRECT_URI=http://127.0.0.1:8765/oauth/callback
OURA_SCOPES=email personal daily heartrate workout tag session spo2Daily
OURA_HOST=127.0.0.1
OURA_PORT=8765
OURA_TOKEN_FILE=data/tokens.json
```

### Changing the port

Change:

```env
OURA_PORT=8765
```

to any unused local port, for example:

```env
OURA_PORT=9100
```

The launcher and Python service automatically use the configured port. If you change the port, update `OURA_REDIRECT_URI` to match and add the exact new callback URL to your Oura application.

The service does not require port 8000.

### Changing the bind address

For normal personal use, keep:

```env
OURA_HOST=127.0.0.1
```

This prevents accidental LAN exposure. Only change it when you intentionally need network access and understand the security implications.

## Launcher commands

The repository intentionally has one user-facing PowerShell script:

```powershell
.\start-health.ps1
```

Start:

```powershell
.\start-health.ps1
```

Re-run setup/configuration:

```powershell
.\start-health.ps1 -Setup
```

Pull the latest repository code and dependencies without restarting:

```powershell
.\start-health.ps1 -Update
```

Check status:

```powershell
.\start-health.ps1 -Status
```

Stop the service:

```powershell
.\start-health.ps1 -Stop
```

The launcher is location-independent and does not assume `C:\AI` or another fixed installation directory.

## Oura application setup

Create an Oura API application and configure its Redirect URI to exactly match the local value in `oura.env`.

Default callback:

```text
http://127.0.0.1:8765/oauth/callback
```

The application should be granted the Oura scopes required by the data you want to access. The example configuration lists the currently supported read scopes used by this project.

After the first launch, the browser-based OAuth flow stores tokens locally. Tokens are never intended to be committed to the repository.

## MCP endpoint

Default:

```text
http://127.0.0.1:8765/mcp
```

Health check:

```text
http://127.0.0.1:8765/health
```

Use the configured host and port if you changed them.

## Oura data

The Oura layer is designed around Oura API V2 read collections, including personal information, daily activity, sleep, readiness, stress, resilience, SpO2, cardiovascular age, VO2 max, sleep details, heart rate, workouts, sessions, tags, enhanced tags, rest mode, ring configuration, and battery data where the authorized Oura application exposes the corresponding collection.

The generic Oura data interface supports date/datetime ranges, pagination, record limits, and targeted collection access. Heart-rate and other time-series requests are bounded to prevent accidentally filling an AI model's context window.

## Analytics

The project includes a local analytics layer intended to reduce the amount of raw data that must be supplied to an AI model. It can support personal baselines, rolling trends, anomalies, correlations, period comparisons, sleep debt, sleep regularity, and related derived metrics.

Prefer the compact health-analysis tools for broad questions and raw Oura collection access for targeted investigations.

## Medical/reference integrations

The project can query public reference sources including biomedical literature and clinical terminology/reference services. These are external reference sources and are not a replacement for professional medical care.

Current integrations include sources such as PubMed/NCBI, MedlinePlus, ICD terminology, LOINC, RxTerms, NPI Registry, CMS Coverage, and FDA/openFDA where supported by the installed integration modules.

Optional NCBI settings can be placed in `oura.env`:

```env
NCBI_EMAIL=you@example.com
NCBI_API_KEY=your_key
```

An NCBI API key is optional.

## Webhooks

The local service is fully usable without public webhook ingress. Webhooks are an optional deployment feature for users who want Oura Cloud to notify the service when data changes.

A public HTTPS endpoint is required for Oura Cloud to reach a local machine. Do not expose the MCP service directly to the Internet. Use a secure tunnel/reverse proxy and expose only the intended webhook route.

See `WEBHOOKS.md` for the deployment architecture.

## Security and privacy

Do not commit `oura.env`, OAuth tokens, local databases, or other personal health data.

The repository's `.gitignore` is intended to exclude these files. The default configuration binds to localhost.

The project is designed for read-only access to the user's own Oura data. Do not share OAuth credentials or tokens with other people or services.

## Documentation

- `CONFIGURATION.md` — configuration reference
- `INSTALLATION.md` — installation and troubleshooting
- `MCP_TOOLS.md` — MCP tools/resources
- `INTEGRATIONS.md` — health and medical integrations
- `WEBHOOKS.md` — optional webhook deployment
- `SECURITY.md` — credential and privacy guidance
- `DEVELOPMENT.md` — development notes

## License

See the repository license file. Third-party services and APIs remain subject to their own terms and agreements.
