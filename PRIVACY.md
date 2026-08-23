# Privacy

Personal Health MCP is designed as a local-first application. The project does not operate a central service that receives your health data.

## What is stored locally

Depending on the integrations you enable, the application can store Oura data, OAuth tokens, synchronization state, webhook events, and derived analytics in local files/database storage on your computer.

## What leaves your computer

The application communicates with services you explicitly configure, such as Oura Cloud and public medical/reference APIs such as PubMed/NCBI, MedlinePlus, FDA/openFDA, CMS, and other documented integrations. Requests to those services are subject to their own privacy policies and terms.

The local MCP server is intended to bind to localhost by default. Do not expose it publicly unless you understand the security implications and have configured authentication/network controls appropriately.

## Credentials

Never commit `.env`, `oura.env`, OAuth tokens, databases, or other secrets to source control. The installer creates local configuration files and the repository's `.gitignore` excludes common secret/data files.

## Webhooks

Webhooks are optional. If enabled, an HTTPS endpoint must be reachable by the provider. A tunnel or reverse proxy can expose only the webhook route while keeping the MCP interface local. Webhook payloads and synchronization data can contain sensitive health information and should be treated accordingly.

## Third-party services

This software can connect to third-party services. Using an integration means those services may process the information contained in your requests according to their own policies. Review each provider's current terms and privacy documentation before enabling it.

## No telemetry by default

The application is designed not to send analytics or telemetry to the project maintainer. Local diagnostic logs are for your own troubleshooting.

## Medical data

The software is a data-access and analysis tool. It is not a healthcare provider and does not replace professional medical advice, diagnosis, or treatment.

For questions about data handled by a third-party service, consult that service's current privacy documentation.
