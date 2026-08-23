# Development

The application is organized as a local MCP service with separate Oura, analytics, medical, and FDA integration modules.

## Entry point

`health_mcp.py` registers integration tools and starts the Streamable HTTP MCP application.

## Configuration

Runtime configuration is loaded from `oura.env`. Do not add machine-specific absolute paths to source code.

## Adding a tool

Prefer a small isolated module, explicit input limits, bounded external requests, clear errors, and source attribution. Register the tool from `health_mcp.py`.

## Port handling

The Oura service currently owns the HTTP listener and reads `OURA_HOST` and `OURA_PORT`. The PowerShell launcher reads the same values for status checks and displayed client URLs.

## Testing

Before publishing changes, verify:

1. The server imports successfully.
2. The configured port is honored.
3. `/health` responds.
4. MCP Streamable HTTP starts.
5. OAuth configuration is not logged.
6. Existing tokens remain outside Git.
7. External API failures produce useful errors rather than crashing the server.
