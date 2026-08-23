# Security

This project handles potentially sensitive personal health information. Treat the installation as private infrastructure.

## Credentials

Never commit:

- `oura.env`
- OAuth access/refresh tokens
- local databases
- personal health exports
- API keys

The repository provides `oura.env.example`; the real configuration belongs in `oura.env`.

## Network exposure

The default bind address is `127.0.0.1`. Keep it that way for local-only use.

If webhooks are enabled, expose only the webhook route through a secure HTTPS tunnel/reverse proxy. Do not publish the MCP endpoint directly to the Internet.

## AI access

MCP tools expose the authorized user's data to whatever MCP client/model the user connects. Only connect trusted clients and local models/services.

## Logging

Do not log OAuth secrets, access tokens, refresh tokens, or complete personal-health payloads unnecessarily.

## Medical information

Medical/reference integrations provide information for research and contextual analysis. They should not be represented as a diagnosis or a substitute for a clinician.
