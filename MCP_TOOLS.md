# MCP interface

The server uses MCP Streamable HTTP.

Default endpoint:

`http://127.0.0.1:8765/mcp`

The launcher prints the actual endpoint at startup, including custom host/port settings.

## Oura

- `get_connection_status` — report authorization state without exposing secrets
- `list_available_data` — list supported Oura collections
- `authorize_oura` — produce an OAuth authorization URL
- `get_personal_info` — retrieve authorized profile information
- `get_oura_data` — bounded access to supported Oura V2 collections
- `get_health_snapshot` — compact health context for an AI model
- `get_recent_activity_and_recovery` — combined recent health/activity context
- `disconnect_oura` — remove locally stored Oura tokens

## Analytics

The analytics layer provides tools for personal baselines, rolling trends, anomalies, comparisons, correlations, sleep debt, sleep regularity, and related derived metrics as implemented by the installed analytics module.

## Medical/reference tools

Medical/reference tools provide read-only lookups against supported public sources. They are intended to help an AI retrieve primary/reference information and should preserve source identifiers where available.

## Design principle

Use compact analytical resources for broad questions. Use raw collection tools only when the model needs detailed evidence. This reduces context usage for local models and makes long-term analysis practical.
