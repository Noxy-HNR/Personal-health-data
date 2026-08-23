"""Read-only openFDA tools. No API key is required for normal use."""
from typing import Any
import httpx

BASE = "https://api.fda.gov"

def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    r = httpx.get(f"{BASE}/{path}", params=params, headers={"User-Agent":"Personal-Health-MCP/1.0"}, timeout=30)
    r.raise_for_status()
    return r.json()

def register_fda_tools(mcp):
    @mcp.tool()
    def search_fda_drug_labels(query: str, max_results: int = 5) -> dict[str, Any]:
        """Search FDA drug labeling data for indications, warnings, dosage, interactions and other label information."""
        if not query.strip(): raise ValueError("query is required")
        limit=max(1,min(int(max_results),20))
        data=_get("drug/label.json", {"search":f"openfda.brand_name:{query.strip()} OR openfda.generic_name:{query.strip()}","limit":limit})
        return {"results":data.get("results",[]),"source":"FDA openFDA","source_url":"https://open.fda.gov/"}

    @mcp.tool()
    def search_fda_drug_events(query: str, max_results: int = 10) -> dict[str, Any]:
        """Search FDA FAERS adverse-event reports for a drug or ingredient."""
        if not query.strip(): raise ValueError("query is required")
        limit=max(1,min(int(max_results),20))
        data=_get("drug/event.json", {"search":f"patient.drug.medicinalproduct:{query.strip()}","limit":limit})
        return {"results":data.get("results",[]),"source":"FDA openFDA / FAERS","source_url":"https://open.fda.gov/"}

    @mcp.tool()
    def search_fda_device_events(query: str, max_results: int = 10) -> dict[str, Any]:
        """Search FDA MAUDE medical-device adverse-event reports."""
        if not query.strip(): raise ValueError("query is required")
        limit=max(1,min(int(max_results),20))
        data=_get("device/event.json", {"search":f"device.generic_name:{query.strip()}","limit":limit})
        return {"results":data.get("results",[]),"source":"FDA openFDA / MAUDE","source_url":"https://open.fda.gov/"}
