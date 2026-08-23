"""Unified local-first Personal Health MCP entry point."""
import medical_tools
from fda_tools import register_fda_tools
from oura_service import HOST, PORT, mcp
from analytics_tools import register_analytics_tools
from sync_db import register_sync_tools, init_db
from webhook_tools import register_webhook_tools


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
register_fda_tools(mcp)
register_analytics_tools(mcp)
register_sync_tools(mcp)
register_webhook_tools(mcp)

# Install the compact health snapshot last so the established get_health_snapshot
# name remains available while its response is bounded for LLM context windows.
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
