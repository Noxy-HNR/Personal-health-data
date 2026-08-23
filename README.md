# Personal Health Data / Oura MCP

Local-only Oura API service for giving a local AI assistant access to the owner's Oura Ring data.

The service uses Oura API V2 and OAuth 2.0, then exposes the authorized data through an MCP Streamable HTTP server. Oura's current API documentation identifies OAuth 2.0 as the supported authentication method and recommends server-side OAuth for applications that need refresh tokens. citeturn0search1turn1search0

## Architecture

```text
Oura Cloud
    |
    | OAuth 2.0
    v
127.0.0.1:8765
    |
    | MCP Streamable HTTP
    v
cptr / Open WebUI MCP client
    |
    v
Local Qwen / other local models
```

Port **8765** is used intentionally. Port **8000 is not used** by this service.

## Windows quick start

Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "C:\AI\Personal-health-data\start-oura.ps1"
```

Or download/run the startup script directly after cloning the repository.

On first startup the script creates `oura.env`, opens it in Notepad, and waits for you to enter:

- `OURA_CLIENT_ID`
- `OURA_CLIENT_SECRET`
- `OURA_REDIRECT_URI`

The local credential file is ignored by Git and is never committed. OAuth tokens are stored under `data/`, which is also ignored.

## Oura application settings

The default callback is:

`http://127.0.0.1:8765/oauth/callback`

It must exactly match a Redirect URI configured in your Oura application. The value can be changed in `oura.env` at any time; update the Oura application to match it and restart the service.

Oura's OAuth authorization endpoint is `https://cloud.ouraring.com/oauth/authorize` and its token endpoint is `https://api.ouraring.com/oauth/token`. The authorization-code flow returns an access token and refresh token; refresh tokens are single-use and the service therefore saves the newly returned refresh token whenever it refreshes authentication. citeturn0search1

## MCP connection

Connect cptr/Open WebUI's MCP client to:

`http://127.0.0.1:8765/mcp`

The official MCP Python SDK supports Streamable HTTP and uses `/mcp` as the standard endpoint when the server is hosted this way. citeturn1search1turn1search4

## Tools exposed

- `get_connection_status` — connection state without exposing credentials
- `authorize_oura` — creates an OAuth authorization URL
- `get_personal_info` — personal profile data
- `get_oura_data` — access a supported Oura V2 collection
- `get_health_snapshot` — recent sleep, readiness, activity, stress, resilience, SpO2, cardiovascular-age and VO2-max collections
- `get_recent_activity_and_recovery` — combines recovery/activity metrics with workouts
- `disconnect_oura` — removes locally stored OAuth tokens

The broad snapshot is deliberately separated from detailed time-series access so an LLM can request a compact recent health view first and only retrieve large datasets such as heart-rate or detailed sleep when needed.

## Supported Oura collections

The service includes common V2 collections such as `daily_sleep`, `daily_readiness`, `daily_activity`, `daily_stress`, `daily_resilience`, `daily_spo2`, `daily_cardiovascular_age`, `vO2_max`, `sleep`, `sleep_time`, `heartrate`, `workout`, `session`, `tag`, `enhanced_tag`, `rest_mode_period`, `ring_configuration`, and `ring_battery_level`.

Oura's V2 documentation describes daily summaries, time-series measurements, workouts, tags, sessions, SpO2 and other health data. citeturn2search0

## Local-only design

The MCP server binds to `127.0.0.1` rather than an externally reachable interface. Credentials and OAuth tokens are stored locally and excluded from Git. The service does not send Oura data to a cloud AI model; the intended consumer is the user's locally hosted AI stack.

## Notes

Oura data freshness depends on when the ring has synchronized with Oura Cloud. Oura recommends using webhooks for ongoing update-driven integrations, while historical data can be loaded initially. This first version uses on-demand API reads so it remains simple to run locally; webhook synchronization can be added later. citeturn2search0
