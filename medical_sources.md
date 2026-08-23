# Medical/reference sources

The MCP medical layer uses public reference APIs where possible and does not require separate accounts for normal use.

## Sources

- PubMed / NCBI E-utilities: biomedical literature search and article metadata/abstract retrieval.
- MedlinePlus: consumer-facing health topics and medical reference information.
- ICD-10-CM: U.S. diagnosis code lookup.
- ICD-11: WHO classification lookup where available through the configured service.
- LOINC: laboratory and clinical observation code lookup.
- RxTerms: medication terminology lookup.
- MedlinePlus Connect: patient-facing information for supported clinical codes.
- NPI Registry: U.S. provider/NPI lookup.
- CMS Coverage: Medicare coverage information.
- FDA openFDA: public drug/device safety and labeling datasets.

## Optional NCBI configuration

PubMed works without a key. For higher E-utilities limits, add:

`NCBI_EMAIL=your-email@example.com`

`NCBI_API_KEY=your_ncbi_api_key`

to the local `oura.env`. Never commit that file.

## Adding another source

Medical sources should be implemented as read-only MCP tools under `medical_tools.py` or a dedicated integration module. Prefer official APIs and primary sources. Do not silently treat third-party summaries as authoritative medical guidance.
