# Personal Health Data / Oura MCP

A local-only Oura API V2 service for giving your local AI assistant access to your own Oura Ring data.

The service uses Oura OAuth 2.0 and exposes the authorized read-only data through MCP Streamable HTTP. Oura documents OAuth 2.0 as the supported authentication method and provides a server-side flow with refresh tokens. citeturn0search0turn0search2

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
Local Qwen / Ornith / other local models
```

Port **8765** is used intentionally. Port **8000 is not used** by this service.

## Windows quick start

Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "C:\AI\Personal-health-data\start-oura.ps1"
```

On first startup the script clones/updates this repository, creates a Python virtual environment, creates `oura.env` if necessary, opens it in Notepad, installs dependencies, and starts the service. If `oura.env` already exists, it is preserved and reused.

The local credential file is ignored by Git and is never committed. OAuth tokens and temporary OAuth state under `data/` are also ignored. fileciteturn22file0L2-L2

## Oura application settings

Default callback:

`http://127.0.0.1:8765/oauth/callback`

It must exactly match a Redirect URI configured in your Oura application. Oura requires the redirect URI used in authorization/token exchange to match the registered URI. citeturn0search0

The current Oura V2 documentation lists these OAuth scopes: `email`, `personal`, `daily`, `heartrate`, `workout`, `tag`, `session`, and `spo2Daily`. citeturn0search0turn0search2

The example configuration requests all of them. If Oura's application page grants fewer scopes, edit `OURA_SCOPES` accordingly and re-authorize.

## MCP connection

Connect cptr/Open WebUI to:

`http://127.0.0.1:8765/mcp`

## MCP tools

- `get_connection_status` — authorization state, expiry, scopes and endpoint without exposing secrets
- `list_available_data` — complete list of supported Oura collections
- `authorize_oura` — generates an OAuth authorization URL
- `get_personal_info` — personal profile data
- `get_oura_data` — generic access to every supported Oura V2 read collection, with date/datetime ranges, sparse fields, pagination, latest-sample mode and record limits
- `get_health_snapshot` — compact multi-metric snapshot for AI analysis
- `get_recent_activity_and_recovery` — combined recovery/activity/workout/tag/rest-mode data
- `disconnect_oura` — removes locally stored OAuth tokens

## Oura data exposed

The service covers the current read collections used by Oura V2, including:

- `personal_info`
- `daily_activity`
- `daily_sleep`
- `daily_readiness`
- `daily_stress`
- `daily_resilience`
- `daily_spo2`
- `daily_cardiovascular_age`
- `vO2_max`
- `sleep`
- `sleep_time`
- `heartrate`
- `workout`
- `session`
- `tag`
- `enhanced_tag`
- `rest_mode_period`
- `ring_configuration`
- `ring_battery_level`

Oura's current V2 documentation describes daily summaries, time-series measurements, sleep, activity, readiness, heart rate/HRV, workouts, tags, sessions, SpO2, stress and specialized metrics. citeturn0search2turn3search2

### Pagination

The service automatically follows Oura `next_token` pagination instead of returning only the first page. This is important for historical sleep, workouts, tags, sessions and other collections. A configurable `max_records` limit prevents an accidental LLM request from filling its entire context with data. Oura collections expose cursor pagination through `next_token`. citeturn3search8

### Heart-rate and battery data

Heart-rate and ring-battery queries use ISO-8601 datetimes and are bounded to 30 days per request to avoid oversized time-series requests. Ask the model for separate ranges when analyzing longer periods.

### Historical analysis

The model can request up to 90 days through the built-in health-analysis helpers, or use `get_oura_data` for targeted ranges. The generic collection tool can retrieve larger historical ranges in bounded calls.

## Local-only design

The MCP server binds to `127.0.0.1`, so it is not intentionally exposed to your LAN or the Internet. Your Oura client secret and OAuth tokens stay on the machine and are excluded from Git. The intended consumer is your locally hosted AI stack.

## Webhooks

Oura currently recommends webhooks for update-driven integrations because they reduce polling and provide notifications when new data becomes available. A pure localhost service cannot directly receive Oura Cloud webhooks because the cloud service needs a publicly reachable HTTPS callback. This build therefore uses on-demand reads and is intentionally self-contained for your local setup. Webhook support can be added later if you decide to expose a secure HTTPS endpoint. citeturn0search2

## API limitations

The service only exposes Oura's public V2 read collections. It does not invent access to data that Oura does not expose through a public read endpoint. Oura states that V2 is the current integration point and V1 has been sunset. citeturn0search2
