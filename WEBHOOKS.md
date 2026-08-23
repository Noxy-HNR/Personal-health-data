# Oura Webhooks and local-first synchronization

The service is designed for Oura's recommended pattern: perform an initial historical import, then use webhook notifications to trigger incremental synchronization.

## Important network requirement

The MCP service listens only on `127.0.0.1:8765`. Oura cannot reach localhost. For webhooks, expose only the webhook route through a secure HTTPS reverse proxy or tunnel (for example Cloudflare Tunnel), not the entire local service directly.

Recommended flow:

`Oura Cloud -> HTTPS webhook endpoint -> local webhook receiver -> Oura API fetch -> SQLite -> MCP`

## Security requirements

- Verify Oura webhook signatures using the Oura client secret before processing an event.
- Never put the Oura client secret, access token, or refresh token in GitHub.
- Keep webhook ingress limited to the webhook route.
- Return quickly from webhook requests and process synchronization asynchronously where practical.
- Treat webhook events as notifications, not complete data payloads: fetch the affected Oura resource after verification.
- Make database writes idempotent so repeated notifications do not create duplicates.
- Keep an audit/log trail locally without storing OAuth secrets in logs.

## Oura developer configuration

After deploying the HTTPS tunnel, set the resulting HTTPS webhook URL in the Oura developer application according to Oura's current Webhook Subscription Routes documentation. The exact public URL is deployment-specific, so it is intentionally not hard-coded in this repository.

## Why webhooks are preferred

The normal synchronization strategy should be:

1. OAuth authorization.
2. One historical synchronization.
3. Subscribe to relevant webhook event types.
4. When Oura notifies us, verify the signature.
5. Fetch the changed record(s) from Oura.
6. Upsert them into SQLite.
7. Let MCP analytics query the local database.

This minimizes API polling and avoids repeatedly loading large historical datasets into the model context.
