"""Unified local-first Personal Health MCP entry point."""
import medical_tools
from fda_tools import register_fda_tools
from oura_service import HOST, PORT, mcp
from sync_db import register_sync_tools, init_db
from webhook_tools import register_webhook_tools
from pubmed_tools import register_pubmed_tools

# Harden Oura OAuth before any tools can make API requests. Oura refresh tokens
# are single-use, so concurrent refreshes can otherwise invalidate each other.
import auth_hardening  # noqa: E402

auth_hardening.install()


def _clinical_search(path, query, max_results, sf, df, ef=None):
    params = {
        "terms": query.strip(),
        "sf": sf,
        "df": df,
        "maxList": max(1, min(int(max_results), 100)),
    }
    if ef:
        params["ef"] = ef
    return medical_tools.get(f"{medical_tools.CT}/{path}/v3/search", params).json()


# Clinical Terminology server searches are exposed through medical_tools.
medical_tools.ctsearch = _clinical_search
medical_tools.register_medical_tools(mcp)

# medical_tools no longer defines search_pubmed (moved entirely into
# pubmed_tools.py, which returns compact, evidence-backed results instead of
# metadata-only citations), so there is no old tool registration to remove here.
register_pubmed_tools(mcp, medical_tools)

register_fda_tools(mcp)
register_sync_tools(mcp)
register_webhook_tools(mcp)

# compact_tools.py is the sole Oura analytics module: snapshot tools
# (get_health_snapshot, get_recent_activity_and_recovery) plus the
# trend/comparison/anomaly/correlation/sleep tools migrated from the
# now-deleted analytics_tools.py and health_analysis_tools.py. Every tool in
# it returns pre-aggregated statistics, never raw Oura records.
import compact_tools  # noqa: F401,E402

init_db()


def main() -> None:
    import uvicorn

    app = mcp.streamable_http_app()
    print(f"Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"Oura OAuth: http://{HOST}:{PORT}/oauth/start")
    print(f"Webhook endpoint: http://{HOST}:{PORT}/oura-webhook")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
