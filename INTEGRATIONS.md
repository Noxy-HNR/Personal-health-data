# Integrations

## Oura

Oura API V2 is the primary personal-data integration. OAuth credentials are supplied by the user and stored locally.

## Medical/reference services

The project can use supported public reference APIs such as:

- PubMed / NCBI E-utilities
- MedlinePlus
- ICD terminology services
- LOINC
- RxTerms
- NPI Registry
- CMS Coverage
- FDA/openFDA

These sources provide reference information; they are not automatically merged into the user's personal health database.

## Adding integrations

New integrations should be implemented as isolated modules and registered from `health_mcp.py`. Prefer official APIs, read-only access where possible, explicit source attribution, bounded results, timeouts, and caching where appropriate.

Do not require users to configure credentials for an integration when the upstream service provides a public API that is sufficient for normal use.
