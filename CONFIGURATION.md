# Configuration

The only normal configuration file is `oura.env`. The launcher creates it automatically from `oura.env.example` on first run.

## Server

```env
OURA_HOST=127.0.0.1
OURA_PORT=8765
```

`OURA_PORT` may be changed to any unused local TCP port. If it is changed, update the Oura redirect URI too.

## Oura OAuth

```env
OURA_CLIENT_ID=...
OURA_CLIENT_SECRET=...
OURA_REDIRECT_URI=http://127.0.0.1:8765/oauth/callback
OURA_SCOPES=email personal daily heartrate workout tag session spo2Daily
```

The redirect URI must exactly match an allowed URI in the Oura developer application.

## Local data

```env
OURA_TOKEN_FILE=data/tokens.json
```

OAuth tokens and local personal-health data are runtime state and must not be committed to Git.

## Optional NCBI

```env
NCBI_EMAIL=you@example.com
NCBI_API_KEY=
```

An NCBI key is optional.

## Environment portability

Do not put machine-specific absolute paths in configuration. The launcher resolves the repository directory automatically, so the project can live under any user-selected directory.
